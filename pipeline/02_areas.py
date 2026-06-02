"""
Stage 2: LLM-assisted area extraction via DeepSeek Flash.

Sends the raw A100 page text to Flash, which reasons through the multi-column
layout to correctly pair labels with values. Flash output is authoritative —
the old Python line-by-line fallback has been removed.

Output: output/areas_flash.json
"""

import json
import re
import time
import fitz
from openai import OpenAI, RateLimitError
from pathlib import Path

import logger
from config import (
    PDF_PATH, OUTPUT_DIR,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_FLASH,
    DEEPSEEK_FLASH_INPUT_COST, DEEPSEEK_FLASH_OUTPUT_COST,
)

MAX_RETRIES = 3
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Normalise document-status variants from title blocks to a consistent vocabulary.
_STATUS_MAP = {
    "issue_for_construction": "issue_for_construction",
    "for_construction":       "issue_for_construction",
    "working_drawings":       "working_drawings",
    "planning_application":   "planning_application",
    "for_approval":           "for_approval",
    "ifa":                    "issue_for_construction",
    "ifc":                    "issue_for_construction",
    "da":                     "planning_application",
    "cc":                     "issue_for_construction",
}

_system_prompt: str | None = None


def load_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        path = PROMPTS_DIR / "extract_areas.txt"
        _system_prompt = path.read_text(encoding="utf-8")
        logger.log(f"Loaded prompt: {path}  ({len(_system_prompt)} chars)")
    return _system_prompt


def call_flash(page_text: str) -> tuple[dict, float]:
    """Returns (parsed_json, cost_usd). Raises on total failure."""
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    user_msg = f"Site plan page text (raw PyMuPDF output):\n\n{page_text}"

    for attempt in range(MAX_RETRIES):
        try:
            logger.log(f"DeepSeek Flash call attempt {attempt+1}/{MAX_RETRIES}")
            resp = client.chat.completions.create(
                model=DEEPSEEK_FLASH,
                messages=[
                    {"role": "system", "content": load_prompt()},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=2048,
                temperature=0,
            )
            raw     = resp.choices[0].message.content.strip()
            in_tok  = resp.usage.prompt_tokens
            out_tok = resp.usage.completion_tokens
            cost    = in_tok * DEEPSEEK_FLASH_INPUT_COST + out_tok * DEEPSEEK_FLASH_OUTPUT_COST

            logger.log(f"Tokens: {in_tok} in / {out_tok} out  cost=${cost:.4f}")

            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)

            parsed = json.loads(raw)
            logger.log(f"Flash response parsed OK")
            return parsed, cost

        except RateLimitError:
            wait = 60 * (attempt + 1)
            logger.warn(f"Rate limit — sleeping {wait}s")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.log(f"Raw output:\n{raw[:600]}", indent=1)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(5)
        except Exception as e:
            logger.error(f"API error: {e}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))

    raise RuntimeError("DeepSeek Flash call failed after all retries")


def main(pdf_path: Path, classifications: list[dict], output_dir: Path) -> tuple[dict, float]:
    logger.init(output_dir, "02_areas")

    doc = fitz.open(str(pdf_path))
    site_idx = next(
        (p["page_index"] for p in classifications if p["classification"] == "site_plan"), 2
    )
    title_idx = next(
        (p["page_index"] for p in classifications if p["classification"] == "title_sheet"), 0
    )
    logger.log(f"Site plan page:  {site_idx}  (1-based: p{site_idx+1})")
    logger.log(f"Title page:      {title_idx}  (1-based: p{title_idx+1})")

    site_text  = doc[site_idx].get_text()
    title_text = doc[title_idx].get_text()
    doc.close()

    logger.log(f"Site plan text: {len(site_text)} chars")
    logger.section("Raw site plan text (first 800 chars)")
    logger.log(repr(site_text[:800]), indent=1)

    # Run Flash
    logger.section("Sending to DeepSeek Flash")
    flash_result, cost = call_flash(site_text + "\n\nTitle page text:\n" + title_text)

    flash_areas   = flash_result.get("areas", {})
    flash_project = flash_result.get("project", {})
    overall_reasoning = flash_result.get("overall_reasoning", "")

    logger.section("Flash reasoning")
    logger.log(overall_reasoning, indent=1)

    logger.section("Flash per-field results")
    for f, info in flash_areas.items():
        logger.log(f"  {f:<22}  value={info.get('value')}  reasoning: {info.get('reasoning','')}", indent=1)

    # Build annotated output — Flash only
    def ann(field):
        info = flash_areas.get(field) or {}
        val  = info.get("value")
        if val is None:
            return None
        return {
            "value":      val,
            "unit":       "m2",
            "confidence": 0.98,
            "source":     "A100_area_schedule:flash",
            "reasoning":  info.get("reasoning", ""),
        }

    annotated = {
        "site_area":         ann("site_area"),
        "ground_floor":      ann("ground_floor"),
        "first_floor":       ann("first_floor"),
        "porch":             ann("porch"),
        "outdoor_living":    ann("outdoor_living"),
        "site_coverage_pct": ann("site_coverage_pct"),
        "site_coverage_m2":  ann("site_coverage_m2"),
    }

    # Project metadata — Flash only, status normalised
    raw_status = (flash_project.get("status") or "").lower().strip()
    project = {
        "address":         flash_project.get("address"),
        "client":          flash_project.get("client"),
        "state":           flash_project.get("state"),
        "document_type":   "working_drawings",
        "document_status": _STATUS_MAP.get(raw_status, raw_status),
        "date":            flash_project.get("date"),
    }

    logger.section("Final project metadata")
    for k, v in project.items():
        logger.log(f"  {k:<20} {v}", indent=1)

    logger.log(f"Total cost: ${cost:.4f}")

    result = {
        "project":            project,
        "areas":              annotated,
        "cost_usd":           round(cost, 5),
        "_raw_flash":         flash_areas,
        "_overall_reasoning": overall_reasoning,
    }

    out = output_dir / "areas_flash.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return result, cost


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stage 2b: Flash area extraction")
    parser.add_argument("--pdf", type=Path, default=PDF_PATH,
                        help="Path to PDF (default: config.PDF_PATH)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: config.OUTPUT_DIR)")
    parser.add_argument("--classifications", type=Path, default=None,
                        help="Path to classification JSON (default: <output-dir>/classification_report_flash.json)")
    args = parser.parse_args()

    out_dir = args.output_dir or OUTPUT_DIR
    cl_path = args.classifications or (out_dir / "classification_report_flash.json")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.loads(cl_path.read_text())
    cl = raw["pages"] if isinstance(raw, dict) and "pages" in raw else raw
    main(args.pdf, cl, out_dir)

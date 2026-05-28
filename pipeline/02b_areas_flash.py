"""
Stage 2b: LLM-assisted area extraction via DeepSeek Flash.

Sends the raw A100 page text to Flash, which reasons through the multi-column
layout to correctly pair labels with values.  The final output merges Flash
results (preferred) with the Python line-by-line parser (fallback), taking
the best available value per field.

Output: output/areas_flash.json — same schema as 02_areas.py output.
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


def merge(flash_areas: dict, python_areas: dict) -> tuple[dict, dict]:
    """
    Merge Flash and Python extractions field by field.
    Flash wins if it returned a non-null value; Python fills any gaps.
    Returns (merged_values, source_map).
    """
    fields = ["site_area", "ground_floor", "porch", "outdoor_living",
              "site_coverage_pct", "site_coverage_m2"]
    merged  = {}
    sources = {}

    for f in fields:
        flash_val  = (flash_areas.get(f) or {}).get("value")
        python_val = python_areas.get(f)

        if flash_val is not None:
            merged[f]  = flash_val
            sources[f] = "flash"
        elif python_val is not None:
            merged[f]  = python_val
            sources[f] = "python_fallback"
        else:
            merged[f]  = None
            sources[f] = "missing"

    return merged, sources


def annotate(val, source_tag: str, reasoning: str = "") -> dict | None:
    if val is None:
        return None
    return {
        "value":      val,
        "unit":       "m2",
        "confidence": 0.98 if source_tag == "flash" else 0.85,
        "source":     f"A100_area_schedule:{source_tag}",
        "reasoning":  reasoning,
    }


def diff_vs_python(flash_areas: dict, python_out_path: Path) -> None:
    if not python_out_path.exists():
        logger.log("No areas.json found — skipping diff")
        return

    py_data = json.loads(python_out_path.read_text())
    py_areas = py_data.get("areas", {})

    logger.section("Diff: Flash vs Python parser")
    fields = ["site_area", "ground_floor", "porch", "outdoor_living",
              "site_coverage_pct", "site_coverage_m2"]
    diffs = 0
    for f in fields:
        py_val    = (py_areas.get(f) or {}).get("value")
        flash_val = (flash_areas.get(f) or {}).get("value")
        match = "==" if py_val == flash_val else "!="
        if match == "!=":
            diffs += 1
        logger.log(f"  {f:<22}  python={py_val}  flash={flash_val}  {match}", indent=1)
    logger.log(f"  {diffs} field(s) differ")


def main(pdf_path: Path, classifications: list[dict], output_dir: Path) -> dict:
    logger.init(output_dir, "02b_areas_flash")

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

    # Run Python parser for comparison / fallback
    import importlib.util
    spec = importlib.util.spec_from_file_location("areas", Path(__file__).parent / "02_areas.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    python_raw = mod.parse_areas(site_text)
    logger.section("Python parser raw output")
    for k, v in python_raw.items():
        logger.log(f"  {k:<22}  {v}", indent=1)

    # Merge
    merged_vals, sources = merge(flash_areas, python_raw)
    logger.section("Merged (Flash preferred, Python fallback)")
    for f, val in merged_vals.items():
        logger.log(f"  {f:<22}  {val}  [{sources[f]}]", indent=1)

    # Diff
    diff_vs_python(flash_areas, output_dir / "areas.json")

    # Build annotated output — same schema as 02_areas.py
    def ann(field):
        val       = merged_vals.get(field)
        src       = sources.get(field, "missing")
        reasoning = (flash_areas.get(field) or {}).get("reasoning", "")
        return annotate(val, src, reasoning)

    annotated = {
        "site_area":         ann("site_area"),
        "ground_floor":      ann("ground_floor"),
        "porch":             ann("porch"),
        "outdoor_living":    ann("outdoor_living"),
        "site_coverage_pct": ann("site_coverage_pct"),
        "site_coverage_m2":  ann("site_coverage_m2"),
    }

    # Project metadata — Flash preferred, fallback to Python
    py_meta_mod = mod.parse_project_meta(title_text + "\n" + site_text)
    project = {
        "address":         flash_project.get("address")  or py_meta_mod.get("address"),
        "client":          flash_project.get("client")   or py_meta_mod.get("client"),
        "state":           flash_project.get("state")    or py_meta_mod.get("state"),
        "document_type":   "working_drawings",
        "document_status": flash_project.get("status")   or py_meta_mod.get("document_status"),
        "date":            flash_project.get("date")     or py_meta_mod.get("date"),
    }

    logger.section("Final project metadata")
    for k, v in project.items():
        logger.log(f"  {k:<20} {v}", indent=1)

    logger.log(f"Total cost: ${cost:.4f}")

    result = {
        "project":          project,
        "areas":            annotated,
        "_raw_flash":       flash_areas,
        "_raw_python":      python_raw,
        "_sources":         sources,
        "_overall_reasoning": overall_reasoning,
    }

    out = output_dir / "areas_flash.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return result


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
    cl = json.loads(cl_path.read_text())
    main(args.pdf, cl, out_dir)

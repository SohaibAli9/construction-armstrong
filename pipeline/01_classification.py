"""
Stage 1: LLM-assisted page classification via DeepSeek Flash.

Sends all page texts in a single call so the model has full document context
(e.g. it can distinguish primary vs supplementary proposed plan, resolve
ambiguous titles, and understand the overall drawing set structure).

Output: output/classification_report_flash.json.
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

MAX_RETRIES   = 3
TEXT_PER_PAGE = 600   # chars sent per page — enough for title block + drawing no + scale

PROMPTS_DIR = Path(__file__).parent / "prompts"

VALID_CLASSES = {
    "title_sheet",
    "general_notes",
    "site_plan",
    "existing_plan",
    "proposed_plan_primary",
    "proposed_plan_ff",
    "proposed_plan_supplementary",
    "electrical_plan",
    "rcp",
    "roof_plan",
    "elevations",
    "sections",
    "door_schedule",
    "window_schedule",
    "joinery_detail",
    "shadow_diagram",
    "perspective",
    "irrelevant",
}

_system_prompt: str | None = None


def load_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        path = PROMPTS_DIR / "classify_pages.txt"
        _system_prompt = path.read_text(encoding="utf-8")
        logger.log(f"Loaded prompt: {path}  ({len(_system_prompt)} chars)")
    return _system_prompt

# Standard Australian drawing discipline codes (AS 1100.301).
# Single-letter prefixes like "X 100" from timber dimensions ("100 X 100") are NOT
# valid drawing numbers — restricting to known discipline codes eliminates those.
DISCIPLINE_CODES = 'ACDEFHLMPS'
DRAWING_NO_RE = re.compile(rf'\b([{DISCIPLINE_CODES}])[ \t]*\d{{3}}[a-zA-Z]?\b')

# Common architectural scales used in Australian residential drawings.
# Minimum 1:5 — excludes ratio text like "1:1" or "1:3" found in specifications.
# Includes the full practical range: 1:5 up to 1:500 for site plans.
VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500}
SCALE_RE = re.compile(r'1\s*[:/]\s*(\d+)\b')

DATE_RE = re.compile(r'\b(\d{1,2}/\d{2}/\d{2,4})\b')


def extract_meta_fallback(text: str) -> dict:
    """Regex fallback for drawing_no / scale / date if LLM returns nulls.

    Uses domain-constrained patterns validated against known Australian
    residential drawing conventions to avoid false positives from
    specification text, dimensions, and ratios in the drawing body.
    """
    dn_m    = DRAWING_NO_RE.search(text)
    date_m  = DATE_RE.search(text)

    # Scale: validate denominator against common architectural scales
    scale = None
    for m in SCALE_RE.finditer(text):
        denom = int(m.group(1))
        if denom in VALID_SCALE_DENOMS:
            scale = f"1:{denom}"
            # Prefer the last valid match (title block is at end of page text)
            # Keep iterating to find later matches
            continue

    return {
        "drawing_no": dn_m.group(0)       if dn_m    else None,
        "scale":      scale               if scale   else None,
        "date":       date_m.group(1)     if date_m  else None,
    }


def build_user_message(pages_text: list[tuple[int, str]]) -> str:
    """Format all pages into a single user message.

    Sends head + tail of each page so the title block (always near the end of
    the fitz text stream) is always included alongside the drawing body.
    """
    HEAD = 300
    TAIL = 400
    parts = []
    for idx, text in pages_text:
        if len(text) <= HEAD + TAIL:
            snippet = text.replace("\n", " ").strip()
        else:
            head = text[:HEAD].replace("\n", " ").strip()
            tail = text[-TAIL:].replace("\n", " ").strip()
            snippet = f"{head} [...] {tail}"
        parts.append(f"PAGE {idx} (1-based: p{idx+1}):\n{snippet}")
    return "\n\n---\n\n".join(parts)


def call_flash(user_message: str) -> tuple[list, float]:
    """Returns (parsed_json_list, cost_usd). Raises on total failure."""
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    for attempt in range(MAX_RETRIES):
        try:
            logger.log(f"DeepSeek Flash call attempt {attempt+1}/{MAX_RETRIES}")
            resp = client.chat.completions.create(
                model=DEEPSEEK_FLASH,
                messages=[
                    {"role": "system", "content": load_prompt()},
                    {"role": "user",   "content": user_message},
                ],
                max_tokens=16384,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            in_tok  = resp.usage.prompt_tokens
            out_tok = resp.usage.completion_tokens
            cost    = in_tok * DEEPSEEK_FLASH_INPUT_COST + out_tok * DEEPSEEK_FLASH_OUTPUT_COST

            logger.log(f"Tokens: {in_tok} in / {out_tok} out  cost=${cost:.4f}")
            logger.log(f"Raw response length: {len(raw)} chars")

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)

            parsed = json.loads(raw)
            logger.log(f"Parsed {len(parsed)} page entries from LLM response")
            return parsed, cost

        except RateLimitError:
            wait = 60 * (attempt + 1)
            logger.warn(f"Rate limit — sleeping {wait}s")
            time.sleep(wait)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.log(f"Raw output was:\n{raw[:500]}", indent=1)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(5)
        except Exception as e:
            logger.error(f"API error: {e}")
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))

    raise RuntimeError("DeepSeek Flash call failed after all retries")


def merge_with_fallback(llm_entry: dict, page_idx: int, raw_text: str) -> dict:
    """Ensure all fields are populated; fall back to regex where LLM returned null."""
    classification = llm_entry.get("classification", "irrelevant")
    if classification not in VALID_CLASSES:
        logger.warn(f"p{page_idx+1}: LLM returned unknown class '{classification}' → irrelevant")
        classification = "irrelevant"

    regex_meta = extract_meta_fallback(raw_text)

    drawing_no = llm_entry.get("drawing_no") or regex_meta["drawing_no"]
    scale      = llm_entry.get("scale")      or regex_meta["scale"]
    date       = llm_entry.get("date")       or regex_meta["date"]

    return {
        "page_index":     page_idx,
        "page_label":     page_idx + 1,
        "classification": classification,
        "drawing_no":     drawing_no,
        "scale":          scale,
        "date":           date,
        "text_length":    len(raw_text),
        "reasoning":      llm_entry.get("reasoning", ""),
    }


def diff_vs_regex(flash_pages: list[dict], regex_path: Path) -> None:
    """Log differences between Flash and regex classification for comparison."""
    if not regex_path.exists():
        logger.log("No regex classification_report.json found — skipping diff")
        return

    regex_pages = json.loads(regex_path.read_text())
    regex_by_idx = {p["page_index"]: p for p in regex_pages}

    logger.section("Diff: Flash vs regex classifier")
    diffs = 0
    for fp in flash_pages:
        idx = fp["page_index"]
        rp  = regex_by_idx.get(idx)
        if not rp:
            continue
        if fp["classification"] != rp["classification"]:
            diffs += 1
            logger.log(
                f"  p{idx+1:02d}  regex={rp['classification']:<35}  flash={fp['classification']}",
                indent=1,
            )
    if diffs == 0:
        logger.log("  No differences — Flash agrees with regex on all pages", indent=1)
    else:
        logger.log(f"  {diffs} page(s) differ", indent=1)


def main(pdf_path: Path, output_dir: Path) -> tuple[list[dict], float]:
    logger.init(output_dir, "01_classification")
    logger.log(f"PDF: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    logger.log(f"Pages: {doc.page_count}")

    # Extract text for every page
    pages_text = []
    for i, page in enumerate(doc):
        text = page.get_text()
        pages_text.append((i, text))
        logger.log(f"  p{i+1:02d}  chars={len(text):>5}", indent=1)

    doc.close()

    logger.section("Sending to DeepSeek Flash")
    user_msg = build_user_message(pages_text)
    logger.log(f"User message length: {len(user_msg)} chars")

    llm_results, cost = call_flash(user_msg)

    # Index LLM results by page_index for safe merging
    llm_by_idx = {entry.get("page_index", i): entry for i, entry in enumerate(llm_results)}

    final_pages = []
    logger.section("Final classifications")
    for idx, raw_text in pages_text:
        llm_entry = llm_by_idx.get(idx, {"classification": "irrelevant"})
        merged    = merge_with_fallback(llm_entry, idx, raw_text)
        final_pages.append(merged)
        logger.log(
            f"p{idx+1:02d}  {merged['classification']:<35}  {merged['drawing_no'] or '':>6}"
            f"  scale={merged['scale'] or '':>7}  {merged['reasoning'][:60]}",
            indent=1,
        )

    # Sanity checks
    primary_count = sum(1 for p in final_pages if p["classification"] == "proposed_plan_primary")
    ff_count      = sum(1 for p in final_pages if p["classification"] == "proposed_plan_ff")
    site_count    = sum(1 for p in final_pages if p["classification"] == "site_plan")
    if primary_count == 0:
        logger.warn("No proposed_plan_primary found — room/geometry extraction will fail")
    elif primary_count > 1:
        logger.warn(f"Multiple proposed_plan_primary ({primary_count}) — expected 1 GF plan")
    if ff_count > 0:
        logger.log(f"Multi-storey set: {ff_count} first-floor plan(s) found (proposed_plan_ff)")
    if site_count == 0:
        logger.warn("No site_plan found — area extraction will fail")

    # Compare against regex output
    diff_vs_regex(final_pages, output_dir / "classification_report.json")

    logger.section("Tally")
    tally: dict[str, int] = {}
    for p in final_pages:
        tally[p["classification"]] = tally.get(p["classification"], 0) + 1
    for label, count in sorted(tally.items(), key=lambda x: -x[1]):
        logger.log(f"{label:<35}  {count}", indent=1)

    logger.log(f"Total cost: ${cost:.4f}")

    result = {"pages": final_pages, "cost_usd": round(cost, 5)}
    out = output_dir / "classification_report_flash.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return final_pages, cost


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result, cost = main(PDF_PATH, OUTPUT_DIR)
    print(f"\nDone. {len(result)} pages classified. Cost: ${cost:.4f}")

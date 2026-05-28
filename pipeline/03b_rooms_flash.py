"""
Stage 3b: LLM-assisted room extraction via DeepSeek Flash.

Sends all text spans with positions and font sizes to Flash so it can reason
about which spans are canonical room labels vs legend/annotation duplicates.

Output: output/rooms_flash.json — same schema as 03_rooms.py output.
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
    GT_OVERALL_MM,
)

MAX_RETRIES = 3
PROMPTS_DIR = Path(__file__).parent / "prompts"

_system_prompt: str | None = None


def load_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        path = PROMPTS_DIR / "extract_rooms.txt"
        _system_prompt = path.read_text(encoding="utf-8")
        logger.log(f"Loaded prompt: {path}  ({len(_system_prompt)} chars)")
    return _system_prompt


def extract_spans(page: fitz.Page) -> list[dict]:
    spans = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"].strip()
                if not text:
                    continue
                bbox = span["bbox"]
                spans.append({
                    "label": text,
                    "x_pt":  round((bbox[0] + bbox[2]) / 2, 1),
                    "y_pt":  round((bbox[1] + bbox[3]) / 2, 1),
                    "size":  round(span.get("size", 0), 2),
                })
    return spans


def build_user_message(spans: list[dict], page_w: float, page_h: float) -> str:
    lines = [
        f"Page dimensions: {page_w:.0f} x {page_h:.0f} pts",
        f"Total spans: {len(spans)}",
        "",
        "Spans (label | x_pt | y_pt | size):",
    ]
    for s in spans:
        lines.append(f"  {s['label']!r:<35}  x={s['x_pt']:>7.1f}  y={s['y_pt']:>7.1f}  size={s['size']:>5.2f}")
    return "\n".join(lines)


def call_flash(user_message: str) -> tuple[dict, float]:
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
                max_tokens=6000,
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


def diff_vs_python(flash_rooms: dict, python_out_path: Path) -> None:
    if not python_out_path.exists():
        logger.log("No rooms.json found — skipping diff")
        return

    py_rooms = json.loads(python_out_path.read_text()).get("rooms", {})
    logger.section("Diff: Flash vs Python room counts")
    all_types = set(flash_rooms) | set(py_rooms)
    diffs = 0
    for rtype in sorted(all_types):
        py_count    = py_rooms.get(rtype, {}).get("count", 0)
        flash_count = flash_rooms.get(rtype, {}).get("count", 0)
        match = "==" if py_count == flash_count else "!="
        if match == "!=":
            diffs += 1
        logger.log(f"  {rtype:<18}  python={py_count}  flash={flash_count}  {match}", indent=1)
    logger.log(f"  {diffs} type(s) differ")


def main(pdf_path: Path, classifications: list[dict], output_dir: Path) -> dict:
    logger.init(output_dir, "03b_rooms_flash")

    doc = fitz.open(str(pdf_path))
    plan_idx = next(
        (p["page_index"] for p in classifications if p["classification"] == "proposed_plan_primary"),
        5,
    )
    page     = doc[plan_idx]
    page_h   = page.rect.height
    page_w   = page.rect.width
    logger.log(f"Page index {plan_idx}  (1-based: p{plan_idx+1})")
    logger.log(f"Page dims: {page_w:.1f} x {page_h:.1f} pts")

    spans = extract_spans(page)
    doc.close()
    logger.log(f"Spans extracted: {len(spans)}")

    logger.section("Size distribution of all spans")
    from collections import Counter
    size_buckets = Counter(round(s["size"]) for s in spans)
    for sz, cnt in sorted(size_buckets.items()):
        logger.log(f"  size ~{sz:>3}pt  → {cnt} spans", indent=1)

    logger.section("Sending to DeepSeek Flash")
    user_msg = build_user_message(spans, page_w, page_h)
    logger.log(f"User message: {len(user_msg)} chars  ({len(spans)} spans)")

    flash_result, cost = call_flash(user_msg)

    flash_rooms     = flash_result.get("rooms", {})
    flash_centroids = flash_result.get("canonical_centroids", [])
    ignored         = flash_result.get("ignored_spans", [])
    reasoning       = flash_result.get("overall_reasoning", "")

    logger.section("Flash overall reasoning")
    logger.log(reasoning, indent=1)

    logger.section("Flash room counts")
    for rtype, info in flash_rooms.items():
        logger.log(f"  {rtype:<18}  count={info.get('count')}  labels={info.get('labels', '')}", indent=1)

    logger.section(f"Canonical centroids ({len(flash_centroids)})")
    for c in flash_centroids:
        logger.log(
            f"  {c.get('label')!r:<25}  type={c.get('type'):<15}  "
            f"({c.get('x_pt'):.1f}, {c.get('y_pt'):.1f})  "
            f"size={c.get('size'):.1f}  — {c.get('reasoning','')}",
            indent=1,
        )

    logger.section(f"Ignored spans ({len(ignored)})")
    for s in ignored:
        logger.log(f"  {s}", indent=1)

    # Also pull dimension strings from raw spans (unchanged from Python logic)
    DIM_RE = re.compile(r'^\d{3,5}$')
    dim_strings = [
        {"value": int(s["label"]), "x_pt": s["x_pt"], "y_pt": s["y_pt"]}
        for s in spans
        if DIM_RE.fullmatch(s["label"]) and 100 <= int(s["label"]) <= 50000
    ]
    logger.log(f"Dimension strings extracted: {len(dim_strings)}")
    if GT_OVERALL_MM:
        exact_target = [d for d in dim_strings if d["value"] == GT_OVERALL_MM]
        if exact_target:
            logger.log(f"{GT_OVERALL_MM} FOUND at ({exact_target[0]['x_pt']:.1f}, {exact_target[0]['y_pt']:.1f})")
        else:
            logger.warn(f"{GT_OVERALL_MM} NOT FOUND in dimension strings")
    elif dim_strings:
        largest = max(dim_strings, key=lambda d: d["value"])
        logger.log(f"No GT_OVERALL_MM set — largest dim string: {largest['value']} at ({largest['x_pt']:.1f}, {largest['y_pt']:.1f})")

    diff_vs_python(flash_rooms, output_dir / "rooms.json")

    logger.log(f"Total cost: ${cost:.4f}")

    result = {
        "plan_page_index":    plan_idx,
        "page_height_pt":     page_h,
        "page_width_pt":      page_w,
        "total_spans":        len(spans),
        "rooms":              flash_rooms,
        "room_centroids":     flash_centroids,
        "dimension_strings":  dim_strings,
        "_ignored_spans":     ignored,
        "_overall_reasoning": reasoning,
    }

    out = output_dir / "rooms_flash.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return result


if __name__ == "__main__":
    import argparse
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="Stage 3b: Flash room extraction")
    parser.add_argument(
        "--classifications",
        type=Path,
        default=OUTPUT_DIR / "classification_report_flash.json",
        help="Path to classification JSON (default: output/classification_report_flash.json)",
    )
    args = parser.parse_args()

    cl = json.loads(args.classifications.read_text())
    main(PDF_PATH, cl, OUTPUT_DIR)

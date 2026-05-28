"""Stage 4: Extract wall geometry from A201 via vector path analysis.

Wall extraction:
  This CAD PDF draws walls as individual l×1 single-segment paths (not closed
  polylines or filled polygons).  Filter D targets these directly:
    - dark stroke color
    - stroke width ≥ 0.45pt  (annotations/dim-lines use 0.24pt, walls use 0.48–0.96pt)
    - single l×1 item
    - extent ≥ 15pt  (eliminates tick marks and hatch cells)
    - centroid within plan bounds (eliminates title block, site boundary, dim rows)

  Colinear segments are merged into wall objects: horizontal grouped by y-bucket,
  vertical grouped by x-bucket, gap tolerance = 25pt (< typical door opening ~25pt).

Calibration:
  Flash identifies the dimension line matching GT_OVERALL_MM (or the largest
  dimension string when GT is unknown) and returns a measured mm/pt ratio.
  All coordinate conversions use this measured value; nominal 35.28 is fallback.
"""

import json
import re
import time
import fitz
from collections import defaultdict
from openai import OpenAI, RateLimitError
from pathlib import Path

from config import (
    MM_PER_PT, GT_OVERALL_MM, CALIBRATION_ERROR_THRESHOLD,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_FLASH,
    DEEPSEEK_FLASH_INPUT_COST, DEEPSEEK_FLASH_OUTPUT_COST,
)
import logger

PROMPTS_DIR = Path(__file__).parent / "prompts"

_calib_prompt: str | None = None


def load_calib_prompt() -> str:
    global _calib_prompt
    if _calib_prompt is None:
        _calib_prompt = (PROMPTS_DIR / "calibrate_dimension.txt").read_text(encoding="utf-8")
        logger.log(f"Loaded calibration prompt ({len(_calib_prompt)} chars)")
    return _calib_prompt


# ─── Geometry helpers ─────────────────────────────────────────────────────────

def is_dark(color, threshold: float = 0.35) -> bool:
    if color is None:
        return False
    if isinstance(color, (int, float)):
        return color < threshold
    try:
        return all(c < threshold for c in color)
    except TypeError:
        return False


def rect_max_extent(rect) -> float:
    return max(abs(rect[2] - rect[0]), abs(rect[3] - rect[1]))


def rect_centroid(rect) -> tuple[float, float]:
    return (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2


def rect_area(rect) -> float:
    return abs((rect[2] - rect[0]) * (rect[3] - rect[1]))


def aspect_ratio(rect) -> float:
    w = abs(rect[2] - rect[0])
    h = abs(rect[3] - rect[1])
    return w / h if h > 0 else 999.0


def items_summary(items: list) -> str:
    counts: dict[str, int] = {}
    for item in (items or []):
        k = item[0] if item else "?"
        counts[k] = counts.get(k, 0) + 1
    return "  ".join(f"{k}×{v}" for k, v in sorted(counts.items()))


# ─── Plan bounds from room centroids ─────────────────────────────────────────

def compute_plan_bounds(rooms_data: dict, margin_pt: float = 40.0) -> dict | None:
    centroids = rooms_data.get("room_centroids", [])
    if not centroids:
        return None
    xs = [c["x_pt"] for c in centroids if "x_pt" in c]
    ys = [c["y_pt"] for c in centroids if "y_pt" in c]
    if not xs:
        return None
    bounds = {
        "x0": min(xs) - margin_pt,
        "y0": min(ys) - margin_pt,
        "x1": max(xs) + margin_pt,
        "y1": max(ys) + margin_pt,
    }
    logger.log(
        f"Plan bounds (pts): x={bounds['x0']:.0f}–{bounds['x1']:.0f}  "
        f"y={bounds['y0']:.0f}–{bounds['y1']:.0f}  (margin={margin_pt}pt)"
    )
    return bounds


def within_bounds(rect, bounds: dict) -> bool:
    cx, cy = rect_centroid(rect)
    return bounds["x0"] <= cx <= bounds["x1"] and bounds["y0"] <= cy <= bounds["y1"]


# ─── Wall extraction ──────────────────────────────────────────────────────────

def extract_walls(drawings: list[dict], plan_bounds: dict | None) -> tuple[list[dict], dict]:
    steps: dict[str, int] = {"total": len(drawings)}

    logger.section("Path attribute distribution")
    filled       = sum(1 for d in drawings if d.get("fill") is not None)
    dark_fill    = sum(1 for d in drawings if is_dark(d.get("fill")))
    dark_stroke  = sum(1 for d in drawings if is_dark(d.get("color")))
    l1_paths     = sum(1 for d in drawings
                       if len(d.get("items", [])) == 1 and d["items"][0][0] == "l")
    logger.log(f"Total: {len(drawings)}  filled: {filled}  dark_fill: {dark_fill}  "
               f"dark_stroke: {dark_stroke}  l×1: {l1_paths}")

    width_bands: dict[str, int] = {"0": 0, "<0.3": 0, "0.3–0.5": 0, "0.5–1": 0, ">1": 0}
    for d in drawings:
        w = d.get("width") or 0
        if w == 0:        width_bands["0"] += 1
        elif w < 0.3:     width_bands["<0.3"] += 1
        elif w <= 0.5:    width_bands["0.3–0.5"] += 1
        elif w <= 1.0:    width_bands["0.5–1"] += 1
        else:             width_bands[">1"] += 1
    logger.log(f"Stroke widths: {width_bands}")

    extent_bands = {"<10": 0, "10–20": 0, "20–50": 0, "50–100": 0, "100–200": 0, ">200": 0}
    for d in drawings:
        e = rect_max_extent(d["rect"])
        if e < 10:        extent_bands["<10"] += 1
        elif e < 20:      extent_bands["10–20"] += 1
        elif e < 50:      extent_bands["20–50"] += 1
        elif e < 100:     extent_bands["50–100"] += 1
        elif e < 200:     extent_bands["100–200"] += 1
        else:             extent_bands[">200"] += 1
    logger.log(f"Extent distribution: {extent_bands}")

    # ── Legacy filters A/B/C (filled polygons and closed polylines) ───────────
    filter_a = [
        d for d in drawings
        if d.get("fill") is not None and is_dark(d.get("fill"))
        and rect_max_extent(d["rect"]) > 30
    ]
    filter_b = [
        d for d in drawings
        if d.get("fill") is None and is_dark(d.get("color"))
        and (d.get("width") or 0) > 0.2
        and len(d.get("items", [])) >= 4
        and rect_max_extent(d["rect"]) > 30
    ]
    logger.log(f"Filter A (dark fill + extent>30pt):              {len(filter_a)}")
    logger.log(f"Filter B (dark stroke + ≥4 items + extent>30pt): {len(filter_b)}")
    steps.update({"filter_a": len(filter_a), "filter_b": len(filter_b)})

    # ── Filter D: l×1 single segments (the actual walls) ─────────────────────
    logger.section("Filter D: l×1 single-segment walls")

    d_step1 = [
        d for d in drawings
        if len(d.get("items", [])) == 1 and d["items"][0][0] == "l"
        and is_dark(d.get("color"))
        and (d.get("width") or 0) >= 0.45      # 0.24pt = annotations, 0.48pt+ = walls
        and rect_max_extent(d["rect"]) >= 15    # eliminates tick marks
    ]
    logger.log(f"  l×1 + dark + width≥0.45 + extent≥15pt: {len(d_step1)}")
    steps["filter_d_pre_bounds"] = len(d_step1)

    if plan_bounds:
        d_step2 = [d for d in d_step1 if within_bounds(d["rect"], plan_bounds)]
        logger.log(f"  After plan-bounds clip: {len(d_step2)}")
    else:
        d_step2 = d_step1
        logger.warn("  No plan bounds — skipping spatial clip")
    steps["filter_d_post_bounds"] = len(d_step2)

    # Log width breakdown of surviving D candidates
    w_counts: dict[str, int] = {}
    for d in d_step2:
        wk = f"{d.get('width') or 0:.2f}pt"
        w_counts[wk] = w_counts.get(wk, 0) + 1
    logger.log(f"  Width breakdown: {dict(sorted(w_counts.items()))}")

    # Log sample
    logger.section("Filter D sample (first 8)")
    for i, d in enumerate(d_step2[:8]):
        r = d["rect"]
        logger.log(
            f"  [{i}]  color={d.get('color')}  w={d.get('width')}  "
            f"extent={rect_max_extent(r):.1f}pt  "
            f"rect=[{r[0]:.1f},{r[1]:.1f},{r[2]:.1f},{r[3]:.1f}]",
            indent=1,
        )

    steps["filter_d_final"] = len(d_step2)

    # ── Choose: prefer D if it has enough walls, else fall back to A+B ────────
    if len(d_step2) >= 20:
        logger.log(f"Using Filter D ({len(d_step2)} segments)")
        chosen = d_step2
        wall_source = "filter_d_line_segments"
    else:
        ab = list({id(d): d for d in filter_a + filter_b}.values())
        if len(ab) >= 20:
            logger.log(f"Filter D insufficient — using A+B ({len(ab)} polygons)")
            chosen = ab
            wall_source = "filter_ab_polygons"
        else:
            best = max([(d_step2, "d"), (filter_a, "a"), (filter_b, "b")], key=lambda x: len(x[0]))
            chosen, wall_source = best[0], f"best_available_{best[1]}"
            logger.warn(f"No filter hit ≥20 — best: {wall_source} ({len(chosen)})")

    steps["final"] = len(chosen)
    steps["wall_source"] = wall_source
    logger.log(f"Final wall source: {wall_source}  count: {len(chosen)}")
    return chosen, steps


# ─── Colinear segment merging ─────────────────────────────────────────────────

def merge_colinear(segments: list[dict], gap_tol_pt: float = 25.0) -> list[dict]:
    """
    Group l×1 segments by orientation and position, merge across small gaps.
    Returns wall objects with endpoints and orientation.
    Gap tolerance = 25pt ≈ 880mm at 35mm/pt — merges across narrow gaps but not door openings.
    """
    if not segments:
        return []

    H_TOL = 1.5   # pts: rect height must be < this to be horizontal
    V_TOL = 1.5   # pts: rect width must be < this to be vertical

    horiz: list[dict] = []
    vert:  list[dict] = []
    other: list[dict] = []

    for d in segments:
        r = d["rect"]
        h = abs(r[3] - r[1])
        w = abs(r[2] - r[0])
        if h <= H_TOL:
            horiz.append(d)
        elif w <= V_TOL:
            vert.append(d)
        else:
            other.append(d)

    logger.log(f"Colinear merge input: {len(horiz)} horizontal  {len(vert)} vertical  {len(other)} diagonal/other")

    def merge_axis(segs: list[dict], axis: str) -> list[dict]:
        """
        axis='h': group by y-center, merge x-extents.
        axis='v': group by x-center, merge y-extents.
        """
        if not segs:
            return []
        # Bucket by position on the grouping axis (0.5pt resolution)
        buckets: dict[int, list] = defaultdict(list)
        for d in segs:
            r = d["rect"]
            if axis == "h":
                key = round((r[1] + r[3]))   # y-center × 2 → integer bucket
            else:
                key = round((r[0] + r[2]))   # x-center × 2 → integer bucket
            buckets[key].append(d)

        merged = []
        for key, group in buckets.items():
            pos = key / 2.0   # restore to pts
            stroke_w = max((d.get("width") or 0.48) for d in group)

            if axis == "h":
                # Sort by x0, merge in x
                group.sort(key=lambda d: d["rect"][0])
                cur_a = group[0]["rect"][0]
                cur_b = group[0]["rect"][2]
                for d in group[1:]:
                    r = d["rect"]
                    if r[0] <= cur_b + gap_tol_pt:
                        cur_b = max(cur_b, r[2])
                    else:
                        merged.append({
                            "x0_pt": cur_a, "y0_pt": pos,
                            "x1_pt": cur_b, "y1_pt": pos,
                            "stroke_w_pt": stroke_w,
                            "orientation": "horizontal",
                            "length_pt": cur_b - cur_a,
                            "segment_count": len([s for s in group if s["rect"][0] <= cur_b]),
                        })
                        cur_a, cur_b = r[0], r[2]
                merged.append({
                    "x0_pt": cur_a, "y0_pt": pos,
                    "x1_pt": cur_b, "y1_pt": pos,
                    "stroke_w_pt": stroke_w,
                    "orientation": "horizontal",
                    "length_pt": cur_b - cur_a,
                    "segment_count": len(group),
                })
            else:
                # Sort by y0, merge in y
                group.sort(key=lambda d: d["rect"][1])
                cur_a = group[0]["rect"][1]
                cur_b = group[0]["rect"][3]
                for d in group[1:]:
                    r = d["rect"]
                    if r[1] <= cur_b + gap_tol_pt:
                        cur_b = max(cur_b, r[3])
                    else:
                        merged.append({
                            "x0_pt": pos, "y0_pt": cur_a,
                            "x1_pt": pos, "y1_pt": cur_b,
                            "stroke_w_pt": stroke_w,
                            "orientation": "vertical",
                            "length_pt": cur_b - cur_a,
                            "segment_count": len([s for s in group if s["rect"][1] <= cur_b]),
                        })
                        cur_a, cur_b = r[1], r[3]
                merged.append({
                    "x0_pt": pos, "y0_pt": cur_a,
                    "x1_pt": pos, "y1_pt": cur_b,
                    "stroke_w_pt": stroke_w,
                    "orientation": "vertical",
                    "length_pt": cur_b - cur_a,
                    "segment_count": len(group),
                })
        return merged

    merged_h = merge_axis(horiz, "h")
    merged_v = merge_axis(vert, "v")

    logger.log(f"After merge: {len(merged_h)} horizontal walls  {len(merged_v)} vertical walls")
    if merged_h:
        lengths_h = sorted(w["length_pt"] for w in merged_h)
        logger.log(f"  Horizontal lengths (pts): min={lengths_h[0]:.0f}  "
                   f"median={lengths_h[len(lengths_h)//2]:.0f}  max={lengths_h[-1]:.0f}")
    if merged_v:
        lengths_v = sorted(w["length_pt"] for w in merged_v)
        logger.log(f"  Vertical lengths (pts):   min={lengths_v[0]:.0f}  "
                   f"median={lengths_v[len(lengths_v)//2]:.0f}  max={lengths_v[-1]:.0f}")

    return merged_h + merged_v


# ─── Coordinate conversion ────────────────────────────────────────────────────

def wall_to_mm(wall_pt: dict, page_height: float, mm_per_pt: float) -> dict:
    """Convert a merged wall line from PDF points to real-world mm."""
    x0 = wall_pt["x0_pt"] * mm_per_pt
    x1 = wall_pt["x1_pt"] * mm_per_pt
    y0 = (page_height - wall_pt["y0_pt"]) * mm_per_pt   # flip Y
    y1 = (page_height - wall_pt["y1_pt"]) * mm_per_pt

    # Normalise so x0 ≤ x1 and y0 ≤ y1
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)

    return {
        "x1_mm":     round(x0, 1),
        "y1_mm":     round(y0, 1),
        "x2_mm":     round(x1, 1),
        "y2_mm":     round(y1, 1),
        "width_mm":  round(x1 - x0, 1),
        "height_mm": round(y1 - y0, 1),
        "stroke_pt": round(wall_pt["stroke_w_pt"], 3),
        "orientation": wall_pt["orientation"],
        "length_mm": round(wall_pt["length_pt"] * mm_per_pt, 1),
        "type":      "wall_line",
    }


def to_real_coords(rect, page_height: float, mm_per_pt: float) -> dict:
    """Legacy polygon-type wall conversion (for filter A/B results)."""
    x0, y0, x1, y1 = rect
    rx0 = x0 * mm_per_pt
    ry0 = (page_height - y1) * mm_per_pt
    rx1 = x1 * mm_per_pt
    ry1 = (page_height - y0) * mm_per_pt
    return {
        "x1_mm":     round(rx0, 1),
        "y1_mm":     round(ry0, 1),
        "x2_mm":     round(rx1, 1),
        "y2_mm":     round(ry1, 1),
        "width_mm":  round(rx1 - rx0, 1),
        "height_mm": round(ry1 - ry0, 1),
        "stroke_mm": None,
        "type":      "wall_rect",
    }


# ─── Calibration (Flash-assisted) ────────────────────────────────────────────

def find_calibration_candidates(drawings: list[dict], dim_x: float, dim_y: float,
                                x_radius: float = 200.0, y_radius: float = 40.0) -> list[dict]:
    candidates = []
    for i, d in enumerate(drawings):
        r = d["rect"]
        cx, cy = rect_centroid(r)
        w = abs(r[2] - r[0])
        h = abs(r[3] - r[1])
        if abs(cy - dim_y) <= y_radius and abs(cx - dim_x) <= x_radius and w > 10:
            candidates.append({
                "path_id":       i,
                "rect":          [round(v, 1) for v in r],
                "width_pts":     round(d.get("width") or 0, 3),
                "color":         d.get("color"),
                "fill":          d.get("fill"),
                "item_count":    len(d.get("items", [])),
                "items_summary": items_summary(d.get("items", [])),
                "rect_width":    round(w, 1),
                "rect_height":   round(h, 1),
            })
    return candidates


def calibrate_with_flash(candidates: list[dict], dim_pos: dict, target_mm: int) -> dict:
    if not candidates:
        logger.warn("No calibration candidates — using nominal")
        return _nominal_calibration("nominal_no_candidates")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    lines = [
        f"Dimension text '{target_mm}' at PDF point ({dim_pos['x_pt']:.1f}, {dim_pos['y_pt']:.1f}).",
        f"{len(candidates)} candidate paths found:",
        "",
    ]
    for c in candidates:
        lines.append(
            f"  path_id={c['path_id']}  rect={c['rect']}  "
            f"stroke_w={c['width_pts']}  color={c['color']}  fill={c['fill']}  "
            f"items={c['item_count']} ({c['items_summary']})  "
            f"rect_w={c['rect_width']}pt  rect_h={c['rect_height']}pt"
        )
    user_msg = "\n".join(lines)

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_FLASH,
                messages=[
                    {"role": "system", "content": load_calib_prompt()},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=1024,
                temperature=0,
            )
            raw    = resp.choices[0].message.content.strip()
            in_tok = resp.usage.prompt_tokens
            out_tok = resp.usage.completion_tokens
            cost   = in_tok * DEEPSEEK_FLASH_INPUT_COST + out_tok * DEEPSEEK_FLASH_OUTPUT_COST

            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            result = json.loads(raw)

            logger.log(f"Flash calibration: {in_tok}in/{out_tok}out  ${cost:.4f}")
            logger.log(f"  path={result.get('selected_path_id')}  "
                       f"span={result.get('measured_span_pts')}pt  "
                       f"mm/pt={result.get('computed_mm_per_pt')}  "
                       f"confidence={result.get('confidence')}")
            logger.log(f"  reasoning: {result.get('reasoning','')}")

            if result.get("selected_path_id") is None:
                return _nominal_calibration("nominal_flash_no_match",
                                            result.get("reasoning", ""))

            span     = result.get("measured_span_pts")
            mm_pt    = result.get("computed_mm_per_pt")
            if not span or not mm_pt:
                return _nominal_calibration("nominal_flash_incomplete")

            error_pct = abs(mm_pt - MM_PER_PT) / MM_PER_PT * 100

            return {
                "method":             "flash_measured",
                "expected_mm":        target_mm,
                "measured_span_pts":  round(span, 2),
                "computed_mm_per_pt": round(mm_pt, 6),
                "nominal_mm_per_pt":  MM_PER_PT,
                "error_pct":          round(error_pct, 3),
                "flag":               error_pct > CALIBRATION_ERROR_THRESHOLD * 100,
                "confidence":         result.get("confidence", "unknown"),
                "flash_reasoning":    result.get("reasoning", ""),
                "cost_usd":           round(cost, 5),
            }

        except (json.JSONDecodeError, RateLimitError, Exception) as e:
            logger.error(f"Calibration Flash attempt {attempt+1}: {e}")
            if attempt == 2:
                return _nominal_calibration("nominal_flash_error", str(e))
            time.sleep(5)

    return _nominal_calibration()


def calibrate(drawings: list[dict], rooms_data: dict) -> dict:
    dims = rooms_data.get("dimension_strings", [])

    logger.section("Scale calibration")
    logger.log(f"Nominal: 1:100, A3  →  {MM_PER_PT:.6f} mm/pt")

    # Find the calibration dimension: use GT when known, else pick the largest dim string
    if GT_OVERALL_MM:
        target = [d for d in dims if d["value"] == GT_OVERALL_MM]
        target_mm = GT_OVERALL_MM
    else:
        sorted_dims = sorted(dims, key=lambda d: -d["value"])
        target = sorted_dims[:1]
        target_mm = target[0]["value"] if target else None

    if not target or target_mm is None:
        logger.warn("Calibration dimension not found — using nominal calibration")
        return _nominal_calibration("nominal_dim_not_found")

    dim = target[0]
    logger.log(f"Calibration target: {target_mm} mm  at ({dim['x_pt']:.1f}, {dim['y_pt']:.1f})")
    logger.log(f"Expected span at nominal: {target_mm / MM_PER_PT:.1f} pts")

    candidates = find_calibration_candidates(drawings, dim["x_pt"], dim["y_pt"])
    logger.log(f"Calibration candidates: {len(candidates)}")
    for c in candidates:
        logger.log(
            f"  id={c['path_id']}  w={c['rect_width']:.1f}×{c['rect_height']:.1f}pt  "
            f"stroke={c['width_pts']}  cmds={c['items_summary']}",
            indent=1,
        )
    return calibrate_with_flash(candidates, {"x_pt": dim["x_pt"], "y_pt": dim["y_pt"]}, target_mm)


def _nominal_calibration(method: str = "nominal", reasoning: str = "") -> dict:
    return {
        "method":             method,
        "expected_mm":        GT_OVERALL_MM,
        "measured_span_pts":  None,
        "computed_mm_per_pt": MM_PER_PT,
        "nominal_mm_per_pt":  MM_PER_PT,
        "error_pct":          None,
        "flag":               False,
        "flash_reasoning":    reasoning,
    }


# ─── Span validation ─────────────────────────────────────────────────────────

def validate_wall_span(walls_mm: list[dict], expected_mm: float) -> tuple[bool, float]:
    """
    Returns (valid, actual_span_mm).
    Invalid if actual > expected × 1.3 (title-block/site-line contamination)
    or actual < expected × 0.3 (too few walls captured).
    """
    if not walls_mm:
        return False, 0.0
    xs = [w["x1_mm"] for w in walls_mm] + [w["x2_mm"] for w in walls_mm]
    actual = max(xs) - min(xs)
    valid  = (expected_mm * 0.3) <= actual <= (expected_mm * 1.3)
    return valid, actual


# ─── Main ─────────────────────────────────────────────────────────────────────

def main(pdf_path: Path, classifications: list[dict], rooms_data: dict, output_dir: Path) -> dict:
    logger.init(output_dir, "04_geometry")

    doc      = fitz.open(str(pdf_path))
    plan_idx = rooms_data.get("plan_page_index", 5)
    page     = doc[plan_idx]
    page_h   = page.rect.height
    page_w   = page.rect.width
    logger.log(f"Page {plan_idx}  (p{plan_idx+1})  dims: {page_w:.1f}×{page_h:.1f} pts")

    drawings = page.get_drawings()
    doc.close()
    logger.log(f"Total drawing paths: {len(drawings)}")

    plan_bounds = compute_plan_bounds(rooms_data)

    # Calibration (Flash-assisted, independent of wall extraction)
    calibration = calibrate(drawings, rooms_data)
    mm = calibration.get("computed_mm_per_pt") or MM_PER_PT

    # Wall extraction
    raw_walls, filter_steps = extract_walls(drawings, plan_bounds)

    # Colinear merging (only meaningful for l×1 line segments)
    if filter_steps.get("wall_source", "").startswith("filter_d"):
        logger.section("Colinear segment merging")
        merged = merge_colinear(raw_walls)
        walls_mm = [wall_to_mm(w, page_h, mm) for w in merged]
    else:
        walls_mm = [to_real_coords(w["rect"], page_h, mm) for w in raw_walls]

    # Span validation — auto-invalidate if contaminated
    expected_span_mm = calibration.get("expected_mm") or GT_OVERALL_MM
    if expected_span_mm and walls_mm:
        span_valid, actual_span = validate_wall_span(walls_mm, expected_span_mm)
        if not span_valid:
            logger.warn(
                f"Span check FAILED: actual={actual_span:.0f}mm  expected≈{expected_span_mm}mm  "
                f"→ invalidating wall set (forcing to 0)"
            )
            walls_mm = []
        else:
            logger.log(f"Span check: actual={actual_span:.0f}mm  expected≈{expected_span_mm}mm  "
                       f"delta={abs(actual_span - expected_span_mm):.0f}mm  valid={span_valid}")
    elif walls_mm:
        logger.warn("No calibration reference — skipping span check")

    # Room centroids → mm
    room_centroids_mm = []
    for rc in rooms_data.get("room_centroids", []):
        room_centroids_mm.append({
            "label": rc.get("label") or rc.get("type", ""),
            "type":  rc.get("type"),
            "x_mm":  round(rc["x_pt"] * mm, 1),
            "y_mm":  round((page_h - rc["y_pt"]) * mm, 1),
        })

    logger.section("Coordinate conversion summary")
    logger.log(f"mm/pt: {mm:.6f}  (method: {calibration.get('method')})")
    logger.log(f"Walls: {len(walls_mm)}  Room centroids: {len(room_centroids_mm)}")
    if walls_mm:
        xs = [w["x1_mm"] for w in walls_mm] + [w["x2_mm"] for w in walls_mm]
        ys = [w["y1_mm"] for w in walls_mm] + [w["y2_mm"] for w in walls_mm]
        logger.log(f"Wall X: {min(xs):.0f}–{max(xs):.0f} mm  Y: {min(ys):.0f}–{max(ys):.0f} mm")

    if room_centroids_mm:
        logger.section("Room centroids in mm")
        for rc in room_centroids_mm:
            logger.log(f"{rc['label']:<22}  ({rc['x_mm']:.0f}, {rc['y_mm']:.0f}) mm", indent=1)

    use_walls = len(walls_mm) >= 20
    logger.log(f"use_wall_geometry: {use_walls}  ({len(walls_mm)} walls)")

    result = {
        "page_dims_pt":      {"width": page_w, "height": page_h},
        "calibration":       calibration,
        "filter_steps":      filter_steps,
        "use_wall_geometry": use_walls,
        "wall_count":        len(walls_mm),
        "walls":             walls_mm,
        "room_centroids_mm": room_centroids_mm,
    }

    out = output_dir / "geometry.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return result


if __name__ == "__main__":
    import argparse
    from config import PDF_PATH, OUTPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="Stage 4: Wall geometry extraction")
    parser.add_argument("--classifications", type=Path,
                        default=OUTPUT_DIR / "classification_report_flash.json")
    parser.add_argument("--rooms", type=Path,
                        default=OUTPUT_DIR / "rooms.json")
    args = parser.parse_args()

    cl = json.loads(args.classifications.read_text())
    rm = json.loads(args.rooms.read_text())
    main(PDF_PATH, cl, rm, OUTPUT_DIR)

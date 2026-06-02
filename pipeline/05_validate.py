"""Stage 5: Validate extracted data against ground truth and internal checks."""

import json
import time
import re
from pathlib import Path
from openai import OpenAI, RateLimitError
from config import (
    GT_SITE_AREA, GT_DWELLING, GT_PORCH, GT_OUTDOOR,
    GT_COVERAGE_PCT, GT_COVERAGE_M2,
    GT_LIGHTING_DWELLING,
    GT_EXPECTED_ROOMS,
    AREA_DELTA_FLAG_M2, CALIBRATION_ERROR_THRESHOLD,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_FLASH,
    DEEPSEEK_FLASH_INPUT_COST, DEEPSEEK_FLASH_OUTPUT_COST,
)
import logger

AREA_TOLERANCE     = 0.5   # m²
COVERAGE_TOLERANCE = 0.1   # percentage points

_NARRATIVE_PROMPT: str | None = None


def _load_narrative_prompt() -> str:
    global _NARRATIVE_PROMPT
    if _NARRATIVE_PROMPT is None:
        p = Path(__file__).parent / "prompts" / "validate_narrative.txt"
        _NARRATIVE_PROMPT = p.read_text()
    return _NARRATIVE_PROMPT


def check_area(label: str, extracted, expected, flags: list) -> dict:
    if expected is None:
        val = (extracted.get("value") if isinstance(extracted, dict) else extracted) if extracted else None
        logger.log(f"{label:<25}  no ground truth — extracted={val}", indent=1)
        return {"expected": None, "extracted": val, "delta": None, "status": "SKIP"}

    logger.log(f"{label:<25}  expected={expected}", indent=1)
    if extracted is None:
        flags.append(f"MISSING: {label} not extracted")
        logger.warn(f"{label} not extracted")
        return {"expected": expected, "extracted": None, "delta": None, "status": "MISSING"}

    val = extracted.get("value") if isinstance(extracted, dict) else extracted
    if val is None:
        flags.append(f"MISSING: {label} value is null")
        logger.warn(f"{label} value is null")
        return {"expected": expected, "extracted": None, "delta": None, "status": "MISSING"}

    delta  = abs(val - expected)
    status = "PASS" if delta <= AREA_TOLERANCE else "FAIL"
    logger.log(f"  extracted={val}  delta={delta:.3f}  → {status}", indent=2)
    if status == "FAIL":
        flags.append(f"AREA_MISMATCH: {label} got={val} expected={expected} delta={delta:.2f}")
    return {"expected": expected, "extracted": val, "delta": round(delta, 3), "status": status}


def check_coverage(areas: dict, flags: list) -> dict:
    pct_extracted  = (areas.get("site_coverage_pct") or {}).get("value")
    m2_extracted   = (areas.get("site_coverage_m2")  or {}).get("value")

    results = {}

    if GT_COVERAGE_PCT is None:
        logger.log(f"{'site_coverage_pct':<25}  no ground truth — extracted={pct_extracted}", indent=1)
        results["site_coverage_pct"] = {"expected": None, "extracted": pct_extracted, "status": "SKIP"}
    elif pct_extracted is None:
        flags.append("MISSING: site_coverage_pct not extracted")
        logger.warn("site_coverage_pct not extracted")
        results["site_coverage_pct"] = {"status": "MISSING"}
    else:
        logger.log(f"{'site_coverage_pct':<25}  expected={GT_COVERAGE_PCT}%", indent=1)
        delta  = abs(pct_extracted - GT_COVERAGE_PCT)
        status = "PASS" if delta <= COVERAGE_TOLERANCE else "FAIL"
        logger.log(f"  extracted={pct_extracted}%  delta={delta:.3f}  → {status}", indent=2)
        if status == "FAIL":
            flags.append(f"COVERAGE_MISMATCH: pct got={pct_extracted} expected={GT_COVERAGE_PCT}")
        results["site_coverage_pct"] = {
            "expected": GT_COVERAGE_PCT, "extracted": pct_extracted,
            "delta": round(delta, 3), "status": status,
        }

    if GT_COVERAGE_M2 is None:
        logger.log(f"{'site_coverage_m2':<25}  no ground truth — extracted={m2_extracted}", indent=1)
        results["site_coverage_m2"] = {"expected": None, "extracted": m2_extracted, "status": "SKIP"}
    elif m2_extracted is None:
        flags.append("MISSING: site_coverage_m2 not extracted")
        logger.warn("site_coverage_m2 not extracted")
        results["site_coverage_m2"] = {"status": "MISSING"}
    else:
        logger.log(f"{'site_coverage_m2':<25}  expected={GT_COVERAGE_M2} m²", indent=1)
        delta  = abs(m2_extracted - GT_COVERAGE_M2)
        status = "PASS" if delta <= AREA_TOLERANCE else "FAIL"
        logger.log(f"  extracted={m2_extracted} m²  delta={delta:.3f}  → {status}", indent=2)
        if status == "FAIL":
            flags.append(f"COVERAGE_MISMATCH: m2 got={m2_extracted} expected={GT_COVERAGE_M2}")
        results["site_coverage_m2"] = {
            "expected": GT_COVERAGE_M2, "extracted": m2_extracted,
            "delta": round(delta, 3), "status": status,
        }

    # Internal consistency: computed pct from extracted m2 and site area
    site_val = (areas.get("site_area") or {}).get("value")
    if m2_extracted and site_val:
        computed_pct = round(m2_extracted / site_val * 100, 2)
        stated_pct   = pct_extracted or GT_COVERAGE_PCT  # may be None if both unknown
        if stated_pct is None:
            results["internal_consistency"] = {"computed_pct": computed_pct, "status": "SKIP"}
            return results
        internal_delta = abs(computed_pct - stated_pct)
        consistent = internal_delta <= COVERAGE_TOLERANCE
        logger.log(
            f"  internal consistency: {m2_extracted}/{site_val}*100 = {computed_pct}%  "
            f"stated={stated_pct}%  delta={internal_delta:.3f}  "
            f"→ {'OK' if consistent else 'INCONSISTENT'}",
            indent=2,
        )
        if not consistent:
            flags.append(f"COVERAGE_INTERNAL: computed {computed_pct}% vs stated {stated_pct}%")
        results["internal_consistency"] = {
            "computed_pct": computed_pct, "stated_pct": stated_pct,
            "delta": round(internal_delta, 3),
            "status": "PASS" if consistent else "FAIL",
        }

    return results


def check_room_completeness(rooms_data: dict, flags: list) -> dict:
    if not GT_EXPECTED_ROOMS:
        logger.log("GT_EXPECTED_ROOMS empty — skipping room completeness check", indent=1)
        return {"status": "SKIP"}

    centroids = rooms_data.get("room_centroids", [])
    found: dict[str, int] = {}
    for c in centroids:
        rtype = c.get("type")
        if rtype:
            found[rtype] = found.get(rtype, 0) + 1

    results  = {}
    missing  = []
    wrong_ct = []

    for rtype, expected_count in GT_EXPECTED_ROOMS.items():
        actual = found.get(rtype, 0)
        if actual == 0:
            status = "MISSING"
            missing.append(rtype)
            flags.append(f"ROOM_MISSING: {rtype} not found on A201")
        elif actual < expected_count:
            status = "LOW_COUNT"
            wrong_ct.append(f"{rtype}={actual}(expected≥{expected_count})")
            flags.append(f"ROOM_COUNT_LOW: {rtype} found={actual} expected≥{expected_count}")
        else:
            status = "PASS"
        logger.log(
            f"{rtype:<18}  expected≥{expected_count}  found={actual}  → {status}", indent=1
        )
        results[rtype] = {"expected_min": expected_count, "found": actual, "status": status}

    extra = {t: n for t, n in found.items() if t not in GT_EXPECTED_ROOMS}
    if extra:
        logger.log(f"Extra room types (not in ground truth): {extra}", indent=1)

    total_found    = sum(found.values())
    total_expected = sum(GT_EXPECTED_ROOMS.values())
    logger.log(f"Total rooms found: {total_found}  expected: {total_expected}", indent=1)
    results["_summary"] = {
        "total_found": total_found, "total_expected": total_expected,
        "missing": missing, "wrong_count": wrong_ct,
        "status": "PASS" if not missing and not wrong_ct else "FAIL",
    }
    return results


def check_centroid_bounds(geometry_data: dict, flags: list) -> dict:
    walls     = geometry_data.get("walls", [])
    centroids = geometry_data.get("room_centroids_mm", [])

    if not walls:
        logger.warn("No walls — skipping centroid bounds check")
        return {"status": "SKIP", "reason": "no walls"}

    xs = [w["x1_mm"] for w in walls] + [w["x2_mm"] for w in walls]
    ys = [w["y1_mm"] for w in walls] + [w["y2_mm"] for w in walls]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    logger.log(f"Wall bounds: x={min_x:.0f}–{max_x:.0f}  y={min_y:.0f}–{max_y:.0f} mm", indent=1)

    # Room label text can sit a little outside the wall it labels — 500mm slack is generous.
    TOL = 500
    out_of_bounds = []
    for c in centroids:
        cx, cy = c["x_mm"], c["y_mm"]
        inside = (min_x - TOL) <= cx <= (max_x + TOL) and (min_y - TOL) <= cy <= (max_y + TOL)
        status = "PASS" if inside else "OUT_OF_BOUNDS"
        margin_x = min(cx - min_x, max_x - cx)
        margin_y = min(cy - min_y, max_y - cy)
        logger.log(
            f"{c['label']:<18} ({cx:.0f}, {cy:.0f})  "
            f"margin x={margin_x:.0f} y={margin_y:.0f}  → {status}",
            indent=2,
        )
        if not inside:
            out_of_bounds.append(c["label"])
            flags.append(
                f"CENTROID_OOB: '{c['label']}' at ({cx:.0f},{cy:.0f}) outside wall bounds "
                f"x={min_x:.0f}–{max_x:.0f} y={min_y:.0f}–{max_y:.0f}"
            )

    status = "PASS" if not out_of_bounds else "FAIL"
    logger.log(f"{len(centroids) - len(out_of_bounds)}/{len(centroids)} centroids within bounds", indent=1)
    return {
        "wall_bounds_mm": {"x": [round(min_x), round(max_x)], "y": [round(min_y), round(max_y)]},
        "tolerance_mm":   TOL,
        "total":          len(centroids),
        "out_of_bounds":  out_of_bounds,
        "status":         status,
    }


def flash_narrative(checks: dict, flags: list, geometry_data: dict, areas: dict) -> dict:
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    payload = {
        "checks":            checks,
        "flags":             flags,
        "room_centroids_mm": geometry_data.get("room_centroids_mm", []),
        "calibration":       geometry_data.get("calibration", {}),
        "areas":             areas,
    }
    user_msg = json.dumps(payload, indent=2)

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_FLASH,
                messages=[
                    {"role": "system", "content": _load_narrative_prompt()},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=1024,
                temperature=0,
            )
            raw     = resp.choices[0].message.content.strip()
            in_tok  = resp.usage.prompt_tokens
            out_tok = resp.usage.completion_tokens
            cost    = in_tok * DEEPSEEK_FLASH_INPUT_COST + out_tok * DEEPSEEK_FLASH_OUTPUT_COST

            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            result = json.loads(raw)

            logger.log(f"Flash narrative: {in_tok}in/{out_tok}out  ${cost:.4f}")
            logger.log(f"  confidence={result.get('confidence_score')}  "
                       f"recommendation={result.get('recommendation')}")
            logger.log(f"  anomalies: {result.get('anomalies', [])}")
            return {**result, "cost_usd": round(cost, 5)}

        except (json.JSONDecodeError, RateLimitError, Exception) as e:
            logger.error(f"Flash narrative attempt {attempt+1}: {e}")
            if attempt == 2:
                return {"error": str(e), "confidence_score": None, "recommendation": "review", "cost_usd": 0.0}
            time.sleep(5)

    return {"error": "max retries", "confidence_score": None, "recommendation": "review", "cost_usd": 0.0}


def main(areas_data: dict, rooms_data: dict, geometry_data: dict, output_dir: Path) -> tuple[dict, float]:
    logger.init(output_dir, "05_validate")
    flags  = []
    checks = {}
    areas  = areas_data.get("areas", {})

    logger.section("Area schedule vs ground truth")
    checks["site_area"]      = check_area("site_area",      areas.get("site_area"),     GT_SITE_AREA, flags)
    checks["ground_floor"]   = check_area("ground_floor",   areas.get("ground_floor"),  GT_DWELLING,  flags)
    checks["porch"]          = check_area("porch",          areas.get("porch"),         GT_PORCH,     flags)
    checks["outdoor_living"] = check_area("outdoor_living", areas.get("outdoor_living"),GT_OUTDOOR,   flags)

    doc_status = areas_data.get("project", {}).get("document_status")
    logger.log(f"Document status: {doc_status}", indent=1)

    logger.section("Coverage checks")
    checks["coverage"] = check_coverage(areas, flags)

    logger.section("Area cross-validation: schedule vs lighting calc (A220)")
    gf_val = (areas.get("ground_floor") or {}).get("value")
    if GT_LIGHTING_DWELLING is None:
        logger.log("No GT_LIGHTING_DWELLING — skipping A220 cross-check")
        checks["area_cross_check"] = {"status": "SKIP"}
    elif gf_val is not None:
        delta_lighting = abs(gf_val - GT_LIGHTING_DWELLING)
        status         = "within_tolerance" if delta_lighting <= AREA_DELTA_FLAG_M2 else "FLAG_discrepancy"
        logger.log(f"Schedule dwelling: {gf_val}  lighting calc: {GT_LIGHTING_DWELLING}  delta: {delta_lighting:.2f} m²")
        logger.log(f"Cross-check status: {status}")
        if status != "within_tolerance":
            flags.append(f"LIGHTING_DELTA: {delta_lighting:.2f} m² > {AREA_DELTA_FLAG_M2}")
        checks["area_cross_check"] = {
            "area_schedule_dwelling": gf_val,
            "lighting_calc_dwelling": GT_LIGHTING_DWELLING,
            "delta_m2": round(delta_lighting, 2),
            "note": "~10 m² expected — lighting calc excludes some areas",
            "status": status,
        }

    logger.section("Room completeness vs ground truth A201 list")
    checks["room_completeness"] = check_room_completeness(rooms_data, flags)

    logger.section("Room count sanity")
    rooms = rooms_data.get("rooms", {})
    for rtype in ["bedrooms", "ensuite", "bathroom", "wir", "kitchen", "study"]:
        count = rooms.get(rtype, {}).get("count", 0)
        ok    = 0 <= count <= 10
        logger.log(f"{rtype:<18} count={count}  {'OK' if ok else 'OUT_OF_RANGE'}", indent=1)
        if not ok:
            flags.append(f"ROOM_COUNT: {rtype}={count} out of range")
    beds = rooms.get("bedrooms", {}).get("count", 0)
    checks["bedroom_count"] = {"count": beds, "status": "PASS" if 1 <= beds <= 10 else "FAIL"}

    logger.section("Geometry calibration")
    cal       = geometry_data.get("calibration", {})
    cal_error = cal.get("error_pct") or 0.0
    cal_flag  = cal.get("flag", False)
    mm_per_pt = cal.get("computed_mm_per_pt")
    logger.log(f"error_pct={cal_error}  flag={cal_flag}  mm_per_pt={mm_per_pt}")
    if cal_flag or cal_error > CALIBRATION_ERROR_THRESHOLD * 100:
        flags.append(f"CALIBRATION: error {cal_error:.1f}% exceeds threshold")
    checks["calibration"] = {
        "mm_per_pt":  mm_per_pt,
        "error_pct":  cal_error,
        "confidence": cal.get("confidence"),
        "status": "PASS" if not cal_flag else "FAIL",
    }

    logger.section("Wall geometry")
    wall_count = geometry_data.get("wall_count", 0)
    logger.log(f"Wall polygons: {wall_count}  (need ≥20 for geometry render)")
    if wall_count < 20:
        flags.append(f"GEOMETRY: only {wall_count} wall polygons — SVG fallback active")
    checks["wall_geometry"] = {
        "wall_count": wall_count,
        "status": "PASS" if wall_count >= 20 else "FALLBACK",
    }

    logger.section("Room centroid bounds check")
    checks["centroid_bounds"] = check_centroid_bounds(geometry_data, flags)

    overall = "PASS" if not flags else "FAIL"
    logger.section(f"Deterministic result: {overall}")
    if flags:
        for f in flags:
            logger.log(f"FLAG: {f}", indent=1)
    else:
        logger.log("All checks passed", indent=1)

    logger.section("Flash narrative (reasoning pass)")
    narrative = flash_narrative(checks, flags, geometry_data, areas)
    logger.log(f"Client summary: {narrative.get('client_summary', '')}")

    val_cost = narrative.get("cost_usd", 0.0)

    result = {
        "overall":   overall,
        "checks":    checks,
        "flags":     flags,
        "narrative": narrative,
        "cost_usd":  round(val_cost, 5),
    }
    out = output_dir / "validation.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return result, val_cost


if __name__ == "__main__":
    from config import OUTPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    areas_path = OUTPUT_DIR / "areas_flash.json" if (OUTPUT_DIR / "areas_flash.json").exists() else OUTPUT_DIR / "areas.json"
    rooms_path = OUTPUT_DIR / "rooms_flash.json" if (OUTPUT_DIR / "rooms_flash.json").exists() else OUTPUT_DIR / "rooms.json"
    a = json.loads(areas_path.read_text())
    r = json.loads(rooms_path.read_text())
    g = json.loads((OUTPUT_DIR / "geometry.json").read_text())
    main(a, r, g, OUTPUT_DIR)

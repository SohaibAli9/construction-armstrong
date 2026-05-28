"""Stage 3: Extract room labels and dimension strings from A201 (proposed plan)."""

import json
import re
import fitz
from pathlib import Path
import logger

# ORDER MATTERS: more specific patterns must come before patterns whose
# regex is a substring of the specific one (e.g. outdoor_living before living,
# ensuite before entry, powder_room before porch).
ROOM_LABELS = {
    "outdoor_living": re.compile(r'\bOutdoor\s*Living\b', re.IGNORECASE),
    "living":         re.compile(r'\bLiving\b',           re.IGNORECASE),
    "bedroom":        re.compile(r'\bBed\s*0?(\d)\b',     re.IGNORECASE),
    "wir":            re.compile(r'\bWIR\b',              re.IGNORECASE),
    "ensuite":        re.compile(r'\bENS\b',              re.IGNORECASE),
    "powder_room":    re.compile(r'\bPdr\b',              re.IGNORECASE),
    "bathroom":       re.compile(r'\bBath\b',             re.IGNORECASE),
    "laundry":        re.compile(r'\bLdy\b',              re.IGNORECASE),
    "kitchen":        re.compile(r'\bKitchen\b',          re.IGNORECASE),
    "dining":         re.compile(r'\bDining\b',           re.IGNORECASE),
    "sitting":        re.compile(r'\bSitting\b',          re.IGNORECASE),
    "entry":          re.compile(r'\bEntry\b',            re.IGNORECASE),
    "porch":          re.compile(r'\bPorch\b',            re.IGNORECASE),
    "study":          re.compile(r'\bStudy\b',            re.IGNORECASE),
    "pantry":         re.compile(r'\bPty\b',              re.IGNORECASE),
    "shed":           re.compile(r'\bShed\b',             re.IGNORECASE),
    "garage":         re.compile(r'\bGarage\b',           re.IGNORECASE),
}

DIM_STRING_RE = re.compile(r'^\d{3,5}$')   # standalone 3-5 digit = dimension in mm

# Room labels in the drawing body are rendered at ~9.9 pt.
# Legend rows, revision notes, and title-block annotations are ≤7.5 pt.
ROOM_LABEL_MIN_SIZE = 8.5


def extract_spans(page: fitz.Page) -> list[dict]:
    spans = []
    blocks = page.get_text("dict")["blocks"]
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"].strip()
                if not text:
                    continue
                bbox = span["bbox"]
                spans.append({
                    "text": text,
                    "bbox": bbox,
                    "cx":   (bbox[0] + bbox[2]) / 2,
                    "cy":   (bbox[1] + bbox[3]) / 2,
                    "size": span.get("size", 0),
                })
    return spans


def classify_spans(spans: list[dict]) -> dict:
    room_centroids  = []
    dim_strings     = []
    found_rooms:  dict[str, list] = {}
    unmatched_sample: list[str]   = []
    skipped_small: list[str]      = []

    for span in spans:
        text    = span["text"]
        matched = False

        for room_type, pattern in ROOM_LABELS.items():
            if pattern.search(text):
                if span["size"] < ROOM_LABEL_MIN_SIZE:
                    # Legend / annotation text — log and skip
                    skipped_small.append(
                        f"'{text}'  size={span['size']:.1f}  "
                        f"at ({span['cx']:.0f},{span['cy']:.0f})  [{room_type}]"
                    )
                    matched = True   # prevent falling through to unmatched_sample
                    break

                entry = {
                    "label": text,
                    "type":  room_type,
                    "x_pt":  span["cx"],
                    "y_pt":  span["cy"],
                    "size":  span["size"],
                }
                room_centroids.append(entry)
                found_rooms.setdefault(room_type, []).append(text)
                logger.log(
                    f"ROOM  {room_type:<18} '{text}'  "
                    f"at ({span['cx']:.1f}, {span['cy']:.1f})  size={span['size']:.1f}",
                    indent=1,
                )
                matched = True
                break

        if not matched and DIM_STRING_RE.fullmatch(text):
            val = int(text)
            if 100 <= val <= 50000:
                dim_strings.append({
                    "value": val,
                    "x_pt":  span["cx"],
                    "y_pt":  span["cy"],
                    "bbox":  span["bbox"],
                })

        if not matched and len(unmatched_sample) < 30:
            unmatched_sample.append(f"'{text}' @({span['cx']:.0f},{span['cy']:.0f})")

    logger.section(f"Skipped small-text room matches ({len(skipped_small)} — legend/annotations)")
    for s in skipped_small:
        logger.log(s, indent=1)

    return {
        "room_centroids":    room_centroids,
        "dimension_strings": dim_strings,
        "found_rooms":       found_rooms,
        "unmatched_sample":  unmatched_sample,
        "skipped_small":     skipped_small,
    }


def build_room_summary(found_rooms: dict) -> dict:
    beds = found_rooms.get("bedroom", [])
    return {
        "bedrooms":      {"count": len(beds), "labels": beds},
        "ensuite":       {"count": len(found_rooms.get("ensuite", []))},
        "bathroom":      {"count": len(found_rooms.get("bathroom", []))},
        "powder_room":   {"count": len(found_rooms.get("powder_room", []))},
        "kitchen":       {"count": len(found_rooms.get("kitchen", []))},
        "laundry":       {"count": len(found_rooms.get("laundry", []))},
        "wir":           {"count": len(found_rooms.get("wir", []))},
        "pantry":        {"count": len(found_rooms.get("pantry", []))},
        "study":         {"count": len(found_rooms.get("study", []))},
        "living":        {"count": len(found_rooms.get("living", []))},
        "dining":        {"count": len(found_rooms.get("dining", []))},
        "sitting":       {"count": len(found_rooms.get("sitting", []))},
    }


def main(pdf_path: Path, classifications: list[dict], output_dir: Path) -> dict:
    logger.init(output_dir, "03_rooms")

    doc = fitz.open(str(pdf_path))
    plan_idx = next(
        (p["page_index"] for p in classifications if p["classification"] == "proposed_plan_primary"),
        5,
    )
    page        = doc[plan_idx]
    page_height = page.rect.height
    page_width  = page.rect.width

    logger.log(f"Using page index {plan_idx}  (1-based: p{plan_idx+1})")
    logger.log(f"Page size: {page_width:.1f} x {page_height:.1f} pts")

    spans  = extract_spans(page)
    logger.log(f"Total spans extracted: {len(spans)}")

    logger.section("Room label scan")
    result = classify_spans(spans)

    logger.section("Dimension strings (showing values near 20490)")
    dims_sorted = sorted(result["dimension_strings"], key=lambda d: abs(d["value"] - 20490))
    for d in dims_sorted[:10]:
        logger.log(f"  {d['value']:>6}  at ({d['x_pt']:.1f}, {d['y_pt']:.1f})", indent=1)
    logger.log(f"Total dimension strings: {len(result['dimension_strings'])}")

    logger.section("Unmatched span sample (first 30)")
    for s in result["unmatched_sample"]:
        logger.log(s, indent=1)

    # Overall dimension check
    exact = [d for d in result["dimension_strings"] if d["value"] == 20490]
    if exact:
        logger.log(f"20490 dimension FOUND at ({exact[0]['x_pt']:.1f}, {exact[0]['y_pt']:.1f})")
    else:
        closest = dims_sorted[0] if dims_sorted else None
        logger.warn(f"20490 dimension NOT FOUND. Closest: {closest['value'] if closest else 'none'}")

    room_summary = build_room_summary(result["found_rooms"])

    logger.section("Room summary")
    for rtype, info in room_summary.items():
        logger.log(f"{rtype:<18} count={info['count']}", indent=1)

    doc.close()

    out_data = {
        "plan_page_index":   plan_idx,
        "page_height_pt":    page_height,
        "page_width_pt":     page_width,
        "total_spans":       len(spans),
        "rooms":             room_summary,
        "room_centroids":    result["room_centroids"],
        "dimension_strings": result["dimension_strings"],
    }

    out = output_dir / "rooms.json"
    out.write_text(json.dumps(out_data, indent=2))
    logger.log(f"Written: {out}")
    return out_data


if __name__ == "__main__":
    import argparse
    from config import PDF_PATH, OUTPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = argparse.ArgumentParser(description="Stage 3: Room label extraction")
    parser.add_argument(
        "--classifications",
        type=Path,
        default=OUTPUT_DIR / "classification_report_flash.json",
        help="Path to classification JSON (default: output/classification_report_flash.json)",
    )
    args = parser.parse_args()

    cl = json.loads(args.classifications.read_text())
    main(PDF_PATH, cl, OUTPUT_DIR)

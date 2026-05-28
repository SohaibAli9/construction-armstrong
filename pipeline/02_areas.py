"""Stage 2: Extract area schedule from A100 and project metadata from title sheet."""

import json
import re
import fitz
from pathlib import Path
import logger

COVERAGE_PCT_RE = re.compile(r'(\d+\.?\d*)\s*%')
ADDRESS_RE      = re.compile(
    r'\d+\s+\w[\w\s]+(?:Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Court|Ct|Place|Pl|Way|Lane|Ln)',
    re.IGNORECASE,
)
CLIENT_RE  = re.compile(r'(?:client|owner|prepared\s*for)[:\s]+([A-Z][A-Za-z\s&]+?)(?:\n|$)', re.IGNORECASE)
STATUS_RE  = re.compile(r'(issue\s*for\s*construction|planning\s*application|for\s*construction|ifa)', re.IGNORECASE)

# Ordered label synonyms — first match wins per slot
AREA_LABELS = [
    ("site_area",      re.compile(r'\bSITE\s+AREA\b',          re.IGNORECASE)),
    ("ground_floor",   re.compile(r'\bPROPOSED\s+DWELLING\b',  re.IGNORECASE)),
    ("porch",          re.compile(r'\bPORCH\b',                 re.IGNORECASE)),
    ("outdoor_living", re.compile(r'\bOUTDOOR\s+LIVING\b',      re.IGNORECASE)),
    ("site_coverage",  re.compile(r'\bSITE\s+COVERAGE\b',       re.IGNORECASE)),
]
VALUE_RE = re.compile(r'^\s*(\d[\d,]*\.?\d*)\s*(?:m²|m2)?\s*$')
COVERAGE_LINE_RE = re.compile(r'(\d+\.?\d*)\s*%.*?(\d[\d,]*\.?\d*)\s*(?:m²|m2)', re.IGNORECASE)


def parse_areas(text: str) -> dict:
    """
    Two-pass line-by-line parser.

    get_text() flattens multi-column tables by reading left column first then
    right column, so the area table arrives as all label lines followed by all
    value lines.  We collect labels and values separately, then zip by position.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Find the AREA ANALYSIS block
    start = next((i for i, l in enumerate(lines) if 'AREA ANALYSIS' in l.upper()), None)
    if start is None:
        logger.warn("'AREA ANALYSIS' heading not found in text")
        logger.log(f"First 20 lines: {lines[:20]}", indent=1)
        return {}

    block = lines[start:]
    logger.section(f"Area block (lines {start}–{start+len(block)}, first 30 shown)")
    for i, l in enumerate(block[:30]):
        logger.log(f"  [{start+i:02d}] {repr(l)}", indent=1)

    # Pass 1: collect label slots in document order
    label_slots: list[str] = []   # e.g. ["site_area", "ground_floor", ...]
    seen: set[str] = set()
    for line in block:
        for key, pattern in AREA_LABELS:
            if key not in seen and pattern.search(line):
                label_slots.append(key)
                seen.add(key)
                logger.log(f"  label slot found: {key}  ← '{line}'", indent=1)
                break

    # Pass 2: collect plain numeric value lines in document order
    value_lines: list[str] = []
    for line in block:
        if VALUE_RE.match(line):
            value_lines.append(line)

    logger.log(f"Label slots ({len(label_slots)}): {label_slots}")
    logger.log(f"Value lines ({len(value_lines)}): {value_lines}")

    # Zip labels → values
    areas: dict[str, float | None] = {}
    for key, vline in zip(label_slots, value_lines):
        val = float(VALUE_RE.match(vline).group(1).replace(',', ''))
        areas[key] = val
        logger.log(f"  {key:<20} = {val}", indent=1)

    # Site coverage needs special handling (contains % and m²)
    cov_line = next((l for l in block if '%' in l and 'm' in l.lower()), None)
    if cov_line:
        m = COVERAGE_LINE_RE.search(cov_line)
        if m:
            areas['site_coverage_pct'] = float(m.group(1))
            areas['site_coverage_m2']  = float(m.group(2).replace(',', ''))
            logger.log(f"  site_coverage_pct = {areas['site_coverage_pct']}", indent=1)
            logger.log(f"  site_coverage_m2  = {areas['site_coverage_m2']}", indent=1)
        else:
            logger.warn(f"Coverage line found but regex failed: {repr(cov_line)}")
    elif 'site_coverage' in areas:
        # Value was already picked up by zip; try to split pct vs m²
        logger.warn("site_coverage: no dedicated pct/m² line found, using zipped value as pct")
        areas['site_coverage_pct'] = areas.pop('site_coverage', None)

    if not areas:
        logger.warn("No areas extracted — dumping raw block for inspection")
        logger.log('\n'.join(block[:40]), indent=1)

    return areas


def parse_project_meta(text: str) -> dict:
    addr_m   = ADDRESS_RE.search(text)
    client_m = CLIENT_RE.search(text)
    status_m = STATUS_RE.search(text)
    date_m   = re.search(r'\b(\d{1,2}/\d{2}/\d{2,4})\b', text)
    state_m  = re.search(r'\b(VIC|NSW|QLD|SA|WA|TAS|ACT|NT)\b', text)

    logger.section("Project metadata")
    logger.log(f"address match:  {addr_m.group(0)   if addr_m   else 'NOT FOUND'}", indent=1)
    logger.log(f"client match:   {client_m.group(1) if client_m else 'NOT FOUND'}", indent=1)
    logger.log(f"status match:   {status_m.group(1) if status_m else 'NOT FOUND'}", indent=1)
    logger.log(f"date match:     {date_m.group(1)   if date_m   else 'NOT FOUND'}", indent=1)
    logger.log(f"state match:    {state_m.group(1)  if state_m  else 'NOT FOUND'}", indent=1)

    raw_status = (status_m.group(1) or "").lower() if status_m else None
    status = "planning_application" if raw_status and "planning" in raw_status else "issue_for_construction"

    return {
        "address":         addr_m.group(0).strip() if addr_m else None,
        "client":          client_m.group(1).strip() if client_m else None,
        "state":           state_m.group(1) if state_m else None,
        "document_type":   "working_drawings",
        "document_status": status,
        "date":            date_m.group(1) if date_m else None,
    }


def main(pdf_path: Path, classifications: list[dict], output_dir: Path) -> dict:
    logger.init(output_dir, "02_areas")

    doc = fitz.open(str(pdf_path))

    site_idx  = next((p["page_index"] for p in classifications if p["classification"] == "site_plan"),    2)
    title_idx = next((p["page_index"] for p in classifications if p["classification"] == "title_sheet"),  0)
    logger.log(f"Site plan page index:  {site_idx}  (1-based: p{site_idx+1})")
    logger.log(f"Title sheet page index:{title_idx}  (1-based: p{title_idx+1})")

    site_text  = doc[site_idx].get_text()
    title_text = doc[title_idx].get_text()
    logger.log(f"Site plan text length:  {len(site_text)} chars")
    logger.log(f"Title sheet text length:{len(title_text)} chars")

    # Log the raw area block for inspection
    area_block_start = site_text.upper().find("AREA")
    if area_block_start >= 0:
        logger.section("Raw area block (200 chars around first AREA mention)")
        logger.log(repr(site_text[max(0, area_block_start-20):area_block_start+200]), indent=1)

    areas = parse_areas(site_text)
    meta  = parse_project_meta(title_text + "\n" + doc[0].get_text())

    def annotate(val, source="A100_area_schedule"):
        return {"value": val, "unit": "m2", "confidence": 0.98, "source": source} if val is not None else None

    annotated = {
        "site_area":         annotate(areas.get("site_area")),
        "ground_floor":      annotate(areas.get("ground_floor")),
        "porch":             annotate(areas.get("porch")),
        "outdoor_living":    annotate(areas.get("outdoor_living")),
        "site_coverage_pct": {"value": areas.get("site_coverage_pct"),
                               "confidence": 0.98, "source": "A100_area_schedule"}
                              if areas.get("site_coverage_pct") else None,
        "site_coverage_m2":  annotate(areas.get("site_coverage_m2")),
    }

    logger.section("Extracted areas summary")
    for k, v in annotated.items():
        val_str = str(v["value"]) if v else "MISSING"
        logger.log(f"{k:<25} {val_str}", indent=1)

    doc.close()

    result = {"project": meta, "areas": annotated, "_raw_areas": areas}
    out = output_dir / "areas.json"
    out.write_text(json.dumps(result, indent=2))
    logger.log(f"Written: {out}")
    return result


if __name__ == "__main__":
    import argparse
    from config import PDF_PATH, OUTPUT_DIR

    parser = argparse.ArgumentParser(description="Stage 2: extract areas from PDF")
    parser.add_argument(
        "--classifications",
        type=Path,
        default=OUTPUT_DIR / "classification_report_flash.json",
        help="Path to classification JSON (default: output/classification_report_flash.json)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cl = json.loads(args.classifications.read_text())
    main(PDF_PATH, cl, OUTPUT_DIR)

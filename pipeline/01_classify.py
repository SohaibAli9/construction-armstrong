"""Stage 1: Classify all pages by drawing title extracted from text layer."""

import json
import re
import fitz
from pathlib import Path
import logger

TITLE_PATTERNS = [
    ("title_sheet",                  r"title\s*sheet|project\s*information|cover\s*sheet"),
    ("general_notes",                r"general\s*notes?|specification"),
    ("site_plan",                    r"site\s*plan|area\s*analysis"),
    ("existing_plan",                r"existing\s*plan|demolition\s*plan"),
    ("proposed_plan_primary",        r"proposed\s*plan"),
    ("rcp",                          r"reflected\s*ceiling|ceiling\s*plan|rcp"),
    ("roof_plan",                    r"roof\s*plan"),
    ("electrical_plan",              r"electrical\s*plan|power\s*plan"),
    ("elevations",                   r"elevation"),
    ("sections",                     r"section"),
    ("door_schedule",                r"door\s*schedule"),
    ("window_schedule",              r"window\s*schedule"),
    ("joinery_detail",               r"joinery|detail"),
    ("shadow_diagram",               r"shadow\s*diagram|overshadow"),
    ("perspective",                  r"perspective|render|3d\s*view"),
]

DRAWING_NO_RE = re.compile(r'\b([A-Z]\s*\d{3}[a-zA-Z]?)\b')
SCALE_RE      = re.compile(r'1\s*[:/]\s*(\d+)')
DATE_RE       = re.compile(r'\b(\d{1,2}/\d{2}/\d{2,4})\b')


def classify_page(text: str) -> str:
    t = text.lower()
    for label, pattern in TITLE_PATTERNS:
        if re.search(pattern, t):
            return label
    return "irrelevant"


def extract_meta(text: str) -> dict:
    dn_m    = DRAWING_NO_RE.search(text)
    scale_m = SCALE_RE.search(text)
    date_m  = DATE_RE.search(text)
    return {
        "drawing_no": dn_m.group(0) if dn_m else None,
        "scale":      f"1:{scale_m.group(1)}" if scale_m else None,
        "date":       date_m.group(1) if date_m else None,
    }


def main(pdf_path: Path, output_dir: Path) -> list[dict]:
    logger.init(output_dir, "01_classify")
    logger.log(f"PDF: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    logger.log(f"Pages: {doc.page_count}")

    pages = []
    tally: dict[str, int] = {}

    for i, page in enumerate(doc):
        text  = page.get_text()
        label = classify_page(text)
        meta  = extract_meta(text)

        # Demote second proposed_plan to supplementary (A200 < A201)
        if label == "proposed_plan_primary":
            dn = (meta.get("drawing_no") or "").replace(" ", "")
            if dn == "A200":
                label = "proposed_plan_supplementary"
                logger.log(f"  p{i+1:02d}: downgraded A200 → proposed_plan_supplementary", indent=1)

        tally[label] = tally.get(label, 0) + 1
        entry = {
            "page_index":     i,
            "page_label":     i + 1,
            "classification": label,
            **meta,
            "text_length":    len(text),
        }
        pages.append(entry)
        logger.log(
            f"p{i+1:02d}  {label:<35}  {meta['drawing_no'] or '':>6}"
            f"  scale={meta['scale'] or '':>7}  chars={len(text):>5}",
            indent=1,
        )

    doc.close()

    logger.section("Classification tally")
    for label, count in sorted(tally.items(), key=lambda x: -x[1]):
        logger.log(f"{label:<35}  {count}", indent=1)

    # Sanity checks
    has_site  = any(p["classification"] == "site_plan"             for p in pages)
    has_plan  = any(p["classification"] == "proposed_plan_primary" for p in pages)
    if not has_site:
        logger.warn("No site_plan page found — area extraction may fail")
    if not has_plan:
        logger.warn("No proposed_plan_primary found — room/geometry extraction may fail")

    out = output_dir / "classification_report.json"
    out.write_text(json.dumps(pages, indent=2))
    logger.log(f"Written: {out}")
    return pages


if __name__ == "__main__":
    from config import PDF_PATH, OUTPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = main(PDF_PATH, OUTPUT_DIR)
    print(f"\nDone. {len(results)} pages classified.")

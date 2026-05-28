# ProCalc AI — Architectural PDF Extraction Demo

Extracts structured JSON and an SVG floor plan from Australian residential working drawings using **PyMuPDF only** (no vision API). Targets CAD-exported vector PDFs where the text layer is reliable.

---

## What it does

Given a 30-page A3 working drawing set, the pipeline:

1. Classifies all pages by drawing title
2. Parses the A100 area schedule (site, dwelling, porch, outdoor living, coverage)
3. Extracts the A201 room inventory (labels, types, centroid positions)
4. Extracts wall geometry via vector path analysis and calibrates scale against a known dimension
5. Validates extracted values against ground truth
6. Renders an SVG floor plan with wall lines, labelled room pills, area schedule legend, and scale bar

**Demo PDF:** 58 Locksley Ave, Reservoir VIC 3060 — Mesh Design Projects (30-page A3 set, 1:100 floor plan)

---

## Stack

- Python 3.12 + [uv](https://github.com/astral-sh/uv)
- [PyMuPDF](https://pymupdf.readthedocs.io/) — text and vector extraction
- DeepSeek Flash (`deepseek-chat` via OpenAI SDK) — calibration + validation narrative
- SVG output — no external rendering dependencies

---

## Quick start

```bash
# 1. Drop the PDF into sample/
cp "Mesh Reservoir 620k mid.pdf" sample/

# 2. Set API key
cp /path/to/.env pipeline/.env    # needs DEEPSEEK_API_KEY

# 3. Run the full pipeline
cd pipeline
uv run python run_all.py

# Re-run a single stage (prior stages must be cached)
uv run python run_all.py --only 6

# Re-run from a specific stage
uv run python run_all.py --stage 4
```

---

## Output

All files land in `output/`:

| File | Contents |
|---|---|
| `classification_report.json` | Page → drawing title mapping |
| `areas_flash.json` | Area schedule (site, dwelling, porch, outdoor living, coverage) |
| `rooms_flash.json` | Room inventory (17 rooms, types, centroid positions) |
| `geometry.json` | 131 wall lines (mm coords), calibration, span check result |
| `validation.json` | Rule-based checks + Flash narrative, overall PASS/FAIL |
| `floor_plan_extracted.svg` | Rendered floor plan |
| `extracted_data.json` | Full combined output |

---

## Extraction results (demo PDF)

| Field | Extracted | Ground truth | Match |
|---|---|---|---|
| Site area | 527.14 m² | 527.14 m² | ✓ |
| Dwelling area | 198.07 m² | 198.07 m² | ✓ |
| Porch | 3.06 m² | 3.06 m² | ✓ |
| Outdoor living | 27.18 m² | 27.18 m² | ✓ |
| Coverage | 41.72% | 41.72% | ✓ |
| Wall count | 131 | — | — |
| Calibration error | < 1% | — | ✓ |
| Validation | PASS | — | ✓ |

---

## Architecture notes

- `run_all.py` loads cached `*_flash.json` in preference to plain `*.json` for area and room stages
- Wall filter (`stroke ≥ 0.45pt`) is tuned to Mesh Design Projects' CAD standard — see `CLAUDE.md` for generalisation notes
- Stroke widths are stored as raw PDF pt values (`stroke_pt`) and converted to screen px in the renderer; they are never multiplied by the plan scale factor
- Planning applications (scanned/rasterised PDFs) are Phase 2 scope — not handled by this pipeline

---

## Licence

Private — ProCalc AI demo.

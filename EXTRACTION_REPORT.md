# Extraction Report — Mesh Reservoir 620k mid

**Project:** 58 Locksley Ave, Reservoir VIC 3060  
**Client:** Sellars & Tayton  
**Architect:** Mesh Design Projects (Benjamin Jewell / Matthew Duignan)  
**Drawing set:** 30-page A3 working drawings, Issue for Construction, 13/07/20 Rev E  
**Source PDF:** `Mesh Reservoir 620k mid.pdf`  
**Processed:** 2026-05-28  
**Pipeline:** ProCalc AI — PyMuPDF text/vector extraction, no vision API  
**Overall result:** ✅ PASS — confidence 0.98 — recommendation: proceed

---

## What the pipeline does

The pipeline extracts structured data from a CAD-exported PDF working drawing set using only the embedded text layer and vector geometry (no AI image recognition). It runs in six numbered stages, each writing a cached output file so any stage can be re-run in isolation.

```
Stage 1  →  Classify all 30 pages by drawing title
Stage 2  →  Parse the Area Analysis table from sheet A100
Stage 3  →  Extract room labels and positions from sheet A201
Stage 4  →  Extract wall geometry (vector lines) from sheet A201
Stage 5  →  Validate all extracted data against ground truth
Stage 6  →  Render the floor plan SVG
```

---

## Stage-by-stage detail

### Stage 1 — Page classification
**Scripts:** `01_classify.py`, `01b_classify_flash.py`  
**Output:** `classification_report.json`, `classification_report_flash.json`

Reads `page.get_text()` on every page and matches the drawing title in the text layer (e.g. "A 100 SITE PLAN", "A 201 PROPOSED PLAN"). DeepSeek Flash is used as a second pass to confirm ambiguous pages. Result: every page in the 30-page set is identified by its drawing number and title, and the pages needed by downstream stages (A100 → p3, A201 → p6, A220 → p8) are pinpointed.

---

### Stage 2 — Area schedule extraction
**Scripts:** `02_areas.py` (Flash only)  
**Output:** `areas.json`, `areas_flash.json`

Targets sheet A100 (Site Plan, p3). The AREA ANALYSIS table is multi-column in the PDF text stream, so a two-pass line-by-line parser flattens the columns and reconstructs the label → value pairs. DeepSeek Flash then normalises units and resolves any ambiguous rows. Key values extracted:

| Field | Extracted | Ground truth | Delta |
|---|---|---|---|
| Site area | 527.14 m² | 527.14 m² | 0.00 |
| Dwelling | 198.07 m² | 198.07 m² | 0.00 |
| Porch | 3.06 m² | 3.06 m² | 0.00 |
| Outdoor Living | 27.18 m² | 27.18 m² | 0.00 |
| Site coverage | 41.72% = 219.91 m² | 41.72% = 219.91 m² | 0.00 |

---

### Stage 3 — Room inventory
**Scripts:** `03_rooms.py` (Flash only)  
**Output:** `rooms.json`, `rooms_flash.json`

Targets sheet A201 (Proposed Plan, p6). Uses `page.get_text("dict")` to extract every text span with its bounding box centroid. A size filter of ≥ 8.5pt drops legend annotations and dimension callouts, leaving only room label text. DeepSeek Flash normalises label variants (e.g. "ENS / PDR" split into separate rooms). Result: 17 room labels with (x, y) centroids in PDF points.

| Rooms found (17/17) |
|---|
| Bed 01, Bed 02, Bed 03 |
| WIR, ENS, Bath, Pdr, Ldy |
| Kitchen, Dining, Living, Sitting |
| Entry, Porch, Study, Pty, Outdoor Living |

---

### Stage 4 — Wall geometry extraction + scale calibration
**Script:** `04_geometry.py`  
**Output:** `geometry.json`

Uses `page.get_drawings()` to retrieve every vector path on A201. Filter D keeps only single-segment dark strokes (colour near black, width ≥ 0.45pt, length ≥ 15pt) within the plan bounds (title block excluded by a 40pt margin). Co-linear segments with gaps < 25pt are merged into single wall lines. Result: 131 wall lines in PDF point coordinates.

**Scale calibration:** Flash locates the "20490" overall-dwelling dimension annotation and its associated dimension line on A201. The actual mm/pt ratio is computed from that measured length, giving 34.94 mm/pt vs the nominal 35.28 (0.96% error — within tolerance, high confidence).

**Coordinate system:** `real_mm = pdf_pts × mm_per_pt`. PDF Y-axis is top-down so Y is inverted: `real_y = (page_height_pts − pdf_y) × mm_per_pt`.

> **Known generalisation risk:** the 0.45pt stroke-width threshold is tuned to Mesh Design Projects' CAD export standard (0.48–0.60pt). Other practices using AutoCAD defaults (0.25–0.35pt) will produce zero walls and silently fall back to the centroid render. Fix: auto-detect threshold from stroke-width distribution when ≥ 2 sample documents are available.

---

### Stage 5 — Validation
**Script:** `05_validate.py`  
**Output:** `validation.json`

Rule-based checks against hard-coded ground truth (from CLAUDE.md), followed by a DeepSeek Flash narrative. Checks run:

- Area values (site, dwelling, porch, outdoor living, coverage %, coverage m²) — all delta 0.00
- Internal consistency: `coverage_m2 / site_area = coverage_pct` — confirmed
- Cross-check: A220 lighting calc dwelling (188.48 m²) vs A100 dwelling (198.07 m²) — 9.59 m² gap is expected (lighting calc excludes some areas); flagged `within_tolerance`
- Room completeness: 17/17 expected rooms present, 0 missing
- Bedroom count: 3 ✅
- Calibration error: 0.96% ✅
- Wall count: 131 (≥ 20 threshold, wall render path active) ✅
- Centroid bounds: all 17 room centroids fall within wall bounding box ✅

**Confidence score: 0.98** — API cost for this run: $0.0005

---

### Stage 6 — SVG render
**Script:** `06_render.py`  
**Output:** `floor_plan_extracted.svg`

Renders the extracted data as an SVG floor plan at 1:100 scale on a 1200×800px canvas. Because wall count (131) exceeded the 20-wall threshold and passed the span check (plan width within 0.3×–1.3× of 20490 mm), the primary render path was used: actual wall lines drawn in dark grey. Room labels are overlaid as coloured badges at their centroid positions. An area schedule legend and scale bar are included. Validation status badge ("PASS") is shown top-right.

---

## Output files in this folder

| File | Stage | Description |
|---|---|---|
| `classification_report.json` | 1 | Page index: drawing number, title, page number for all 30 pages (PyMuPDF pass) |
| `classification_report_flash.json` | 1 | Same index confirmed/corrected by DeepSeek Flash |
| `areas.json` | 2 | Raw area table rows as extracted by the line parser |
| `areas_flash.json` | 2 | Normalised area key-value pairs after Flash pass (preferred by downstream stages) |
| `rooms.json` | 3 | Room labels with PDF-point centroids, raw pass |
| `rooms_flash.json` | 3 | Normalised room list after Flash pass (preferred by downstream) |
| `geometry.json` | 4 | 131 wall line segments in mm coordinates + calibration metadata |
| `extracted_data.json` | 4–5 | Master aggregated output — all stage results merged into one document |
| `validation.json` | 5 | Full validation report: per-check pass/fail, confidence score, Flash narrative |
| `extraction_log.txt` | all | Complete console log of the full pipeline run |
| `floor_plan_extracted.svg` | 6 | Rendered floor plan — wall lines + room labels + area schedule legend |
| `EXTRACTION_REPORT.md` | — | This document |

---

## How to re-run

```bash
cd /root/playground/procalc-ai/pipeline
uv run python run_all.py              # full pipeline end-to-end
uv run python run_all.py --stage 4   # re-run from stage 4 onwards (geometry → validate → render)
uv run python run_all.py --only 6    # re-render SVG only (uses cached prior stage outputs)
uv run python 04_geometry.py         # run a single stage directly
```

Requires `pipeline/.env` with `DEEPSEEK_API_KEY`. Mirror from `/root/clients/justin-short/pipeline/pipeline/.env` if not present.

---

## Ground truth reference

| Source | Value |
|---|---|
| A100 site area | 527.14 m² |
| A100 dwelling | 198.07 m² |
| A100 porch | 3.06 m² |
| A100 outdoor living | 27.18 m² |
| A100 coverage | 41.72% = 219.91 m² |
| A201 scale | 1:100 |
| A201 overall dwelling length | 20490 mm |
| A220 dwelling (cross-check) | 188.48 m² (excludes some areas) |
| A220 porch (cross-check) | 1.98 m² |
| A220 outdoor living (cross-check) | 26.57 m² |

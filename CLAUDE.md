# ProCalc AI — Architectural PDF Extraction Demo

Extracts structured JSON + SVG floor plan from Australian residential working drawings using PyMuPDF text/vector analysis (no vision API). Target: CAD-exported PDFs where the text layer is reliable. Stack: Python 3.12, uv, PyMuPDF (fitz), DeepSeek Flash (`deepseek-chat` via OpenAI SDK at `https://api.deepseek.com`).

---

## Run

```
cd pipeline
uv run python run_all.py              # full pipeline
uv run python run_all.py --stage 4   # re-run from stage 4 onwards
uv run python run_all.py --only 6    # single stage (requires prior stages cached)
uv run python 04_geometry.py         # also runnable directly
```

---

## Hard constraints

- **uv only** — never `python`, `pip`, or `poetry` directly.
- **No vision API on working drawings** — PyMuPDF text/vector is sufficient and deterministic; vision is Phase 2 for scanned planning applications.
- **Prompts stay in `prompts/`** — never inline LLM prompt strings in `.py` files; load them lazily at call time.
- **Output goes to `output/`** — never write generated files elsewhere.
- **Fix only what is asked** — do not refactor adjacent code, rename variables, or add features beyond the task scope.

---

## Repo layout

```
sample/          # drop PDF here
output/          # all generated files land here (gitignored)
pipeline/
  config.py      # PDF_PATH, OUTPUT_DIR, ground truth constants
  run_all.py     # orchestrator: --stage N re-runs from N, --only N runs exactly N
  01_classify.py / 01b_classify_flash.py   # page classification
  02_areas.py    / 02b_areas_flash.py      # A100 area schedule
  03_rooms.py    / 03b_rooms_flash.py      # A201 room inventory
  04_geometry.py                           # wall extraction + calibration
  05_validate.py                           # rule-based + Flash narrative
  06_render.py                             # SVG output
  prompts/       # .txt prompt files, one per LLM call
  pyproject.toml
  .env           # DEEPSEEK_API_KEY — mirror from /root/doc-ai-pipeline/pipeline/.env
```

`run_all.py` prefers `*_flash.json` over plain `*.json` when loading cached stage outputs (areas, rooms).

---

## Target PDF + ground truth

`sample/Mesh Reservoir 620k mid.pdf` — 30-page A3 working drawings, 58 Locksley Ave Reservoir VIC 3060, Mesh Design Projects.

Validate extraction against these known values:
- **A100 (p3)** — site 527.14 m², dwelling 198.07 m², porch 3.06 m², outdoor living 27.18 m², coverage 41.72% = 219.91 m²
- **A201 (p6)** — scale 1:100, overall length 20490 mm; rooms: Bed01, Bed02, Bed03, WIR, ENS, Bath, Pdr, Ldy, Living, Kitchen, Dining, Sitting, Entry, Porch, Study, Pty, Outdoor Living
- **A220 (p8)** — dwelling 188.48 m², porch 1.98 m², outdoor living 26.57 m² (cross-check only; excludes some areas)

---

## Algorithm notes

1. `page.get_text()` → classify all 30 pages by drawing title
2. A100 → two-pass line-by-line parser → AREA ANALYSIS table (multi-column flattening)
3. A201 → `get_text("dict")` → room labels + bbox centroids; size filter ≥ 8.5pt drops legend noise
4. A201 → `get_drawings()` → Filter D: single-segment dark paths, width ≥ 0.45pt, extent ≥ 15pt; 40pt margin excludes title block; colinear merge across gaps < 25pt
5. Calibration: Flash locates actual dimension line near "20490"; computes `computed_mm_per_pt` vs nominal 35.28
6. SVG: wall lines if ≥ 20 walls pass span check (0.3×–1.3× of 20490 mm); fallback to centroid boxes

**Scale:** `real_mm = pdf_pts × 35.28`; PDF Y is inverted: `real_y = (page_height_pts − pdf_y) × 35.28`.  
Nominal: `MM_PER_PT = (25.4 / 72) × 100 = 35.2778`.

**Stroke widths:** `stroke_pt` in `geometry.json` is the raw PDF line weight (0.48–0.60pt for Mesh). The renderer converts to screen px via `stroke_pt × (96/72)`. Do not multiply by `mm_per_pt` — that is a plan scale factor, not a unit conversion.

---

## Known generalisation risk — `04_geometry.py`

`width ≥ 0.45pt` is tuned to Mesh Design Projects' CAD export. AutoCAD defaults and other practices use 0.25–0.35pt — those produce zero walls and silently fall back to centroid render.

**Fix when 2+ sample PDFs are available:** compute stroke-width distribution of all dark paths inside plan bounds; find the natural gap above 0.3pt; set threshold at that valley.

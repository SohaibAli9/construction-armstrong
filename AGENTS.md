# ProCalc AI — Architectural PDF Extraction Demo

Extracts structured JSON + SVG floor plan from Australian residential working drawings using PyMuPDF text/vector analysis (no vision API). Target: CAD-exported PDFs where the text layer is reliable. Stack: Python 3.12, uv, PyMuPDF (fitz), DeepSeek Flash (`deepseek-chat` via OpenAI SDK).

---

## Run

```
cd pipeline
uv run python run_all.py                 # full pipeline end-to-end
uv run python run_all.py --stage 4      # re-run from stage 4 onwards
uv run python run_all.py --only 3       # single stage (requires prior stages cached)
uv run python run_all.py --no-anim      # plain terminal output (no Rich dashboard)
uv run python 04_geometry.py            # any stage also runnable directly
```

---

## Hard constraints

- **uv only** — never `python`, `pip`, or `poetry` directly.
- **No vision API on working drawings** — PyMuPDF text/vector is sufficient and deterministic; vision is Phase 2 for scanned planning applications.
- **Prompts stay in `prompts/`** — never inline LLM prompt strings in `.py` files; load them lazily at call time.
- **Output goes to `output/`** (gitignored) — never write generated files elsewhere.
- **Fix only what is asked** — do not refactor adjacent code, rename variables, or add features beyond the task scope.

---

## Repo layout

```
sample/          # drop PDF here
output/          # all generated files land here (gitignored)
pipeline/
  config.py      # PDF_PATH, OUTPUT_DIR, per-PDF ground truth dict
  run_all.py     # orchestrator: --stage N, --only N, --no-anim
  01_classification.py   # page classification (Flash only)
  02_areas.py            # A100 area schedule (Flash only)
  03_rooms.py            # A201 room inventory (Flash only)
  04_geometry.py         # wall extraction + calibration
  05_validate.py         # rule-based + Flash narrative
  06_render.py           # SVG output
  prompts/       # .txt prompt files, one per LLM call
  pyproject.toml
  .venv/         # uv-managed virtualenv (automatic)
```

Every stage writes JSON to `output/<PDF_stem>/`. Stage 3+ outputs all use the Flash variant (`areas_flash.json`, `rooms_flash.json`). The old regex-based scripts have been removed — they were catastrophically wrong on multiple PDFs and never contributed a correct value Flash missed.

---

## Sample PDFs + ground truth

| PDF | Source | Pages | Key pages |
|---|---|---|---|
| `Mesh Reservoir 620k mid.pdf` | Mesh Design Projects | 30 | A100(p3), A201(p6), A220(p8) |
| `DMP Elm Northcote 750k.pdf` | The Makeover Group | 48 | Proposed Site Plan(p6), Proposed GF(p7), Proposed FF(p8) |

Ground truth lives in `config.py` as a `_GROUND_TRUTHS` dict keyed by `PDF_PATH.stem`. Values auto-follow whichever PDF is configured. Makes switching between samples seamless.

### Mesh Reservoir reference values
- **A100** — site 527.14 m², dwelling 198.07 m², porch 3.06 m², outdoor living 27.18 m², coverage 41.72% = 219.91 m²
- **A201** — scale 1:100, overall length 20490 mm; 17 rooms across 16 types (3 bedrooms + 14 single-count types)
- **A220** — dwelling 188.48 m², porch 1.98 m², outdoor living 26.57 m² (cross-check; excludes some areas)

---

## Pipeline stages

| # | Stage | What it does | LLM call? |
|---|---|---|---|
| 1 | Classification | `page.get_text()` → Flash classifies all pages by drawing title | ✅ |
| 2 | Areas | A100 site plan text → Flash extracts area schedule (site, dwelling, porch, coverage, first_floor) | ✅ |
| 3 | Rooms | A201 `get_text("dict")` → Flash identifies canonical room labels from font-size clusters; Python validator checks centroids match counts | ✅ |
| 4 | Geometry | A201 `get_drawings()` → Filter D: single-segment dark paths, width ≥ 0.45pt, extent ≥ 15pt; colinear merge; Flash calibrates scale from dimension line | ✅ |
| 5 | Validation | Rule-based checks vs ground truth + Flash narrative summary | ✅ |
| 6 | SVG render | Wall lines or fallback centroid boxes + room labels + area legend | — |

---

## Algorithm notes

1. **Classification (stage 1).** Classes: `proposed_plan_primary` (GF), `proposed_plan_ff` (upper floor), `site_plan` (has AREA ANALYSIS), `existing_plan`, `elevations`, `sections`, `joinery_detail`, `door_schedule`, `window_schedule`, `electrical_plan`, etc. Downstream stages consume `proposed_plan_primary` and `site_plan` only — `proposed_plan_ff` is classified but not yet processed.

2. **Areas (stage 2).** Flash parses the multi-column AREA ANALYSIS / AREA SCHEDULE table. Also extracts project metadata (address, client, status). Status is normalised via `_STATUS_MAP` (catches `IFC`, `DA`, `CC` abbreviations). Python parser removed — it returned wrong values on 5/6 Mesh fields. Cost: ~$0.0013/run.

3. **Rooms (stage 3).** Flash receives all text spans with positions and font sizes. The prompt uses relative language ("second-largest font size cluster") so it works across architects — Mesh uses 9.9pt labels, DMP uses 7.78pt. After Flash returns, `validate_flash_counts()` checks every centroid type matches its rooms dict count and auto-corrects mismatches (caught 4 on DMP). Schema covers 16 room types — old gap (entry, porch, outdoor_living, hall missing) is closed. Cost: ~$0.003–0.005/run.

4. **Geometry (stage 4).** Walls use Filter D: dark stroke, width ≥ 0.45pt, single-segment l×1, extent ≥ 15pt, centroid within plan bounds (40pt margin excludes title block). Colinear segments merged across gaps < 25pt. Calibration: Flash finds dimension line near the overall-length value. Scale check verifies plan width vs expected — rejects calibration if >2× mismatch.

5. **SVG (stage 6).** Wall lines if ≥ 20 walls pass span check (0.3×–1.3× of expected plan width). Fallback to centroid boxes. Area legend only lists fields with non-null values (handles missing `outdoor_living` gracefully).

---

## Coordinate system

- `real_mm = pdf_pts × mm_per_pt`. PDF Y is top-down inverted: `real_y = (page_height_pts − pdf_y) × mm_per_pt`.
- Nominal `MM_PER_PT = (25.4 / 72) × 100 = 35.2778`. Actual ratio is computed per-document by Flash calibration.
- `stroke_pt` in `geometry.json` is raw PDF line weight — the renderer converts to screen px via `stroke_pt × (96/72)`. Do NOT multiply by `mm_per_pt`.

---

## Known generalisation risks

1. **Wall stroke threshold** (`04_geometry.py`). `width ≥ 0.45pt` is tuned to Mesh Design Projects' CAD export (0.48–0.60pt). AutoCAD defaults use 0.25–0.35pt — those produce zero walls and silently fall back to centroid render. **Fix when 3+ sample PDFs available:** compute stroke-width distribution of all dark paths inside plan bounds; find the natural gap above 0.3pt.

2. **Calibration with no overall dimension.** DMP Elm has no "20490"-style overall dimension — the heuristic picks the largest dim string ("2340", a room dimension) and produces 50% error. `GT_OVERALL_MM` is `None` for DMP. Future work: derive scale from known room-area ratios or find a dimension string that spans the full plan extent.

3. **`proposed_plan_ff` not consumed.** Multi-storey PDFs are classified correctly but the first floor plan isn't processed by stages 2–4. The `first_floor` area field is captured in stage 2; room extraction for FF remains unimplemented.

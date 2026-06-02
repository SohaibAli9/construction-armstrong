# Australian Residential Document Types — Pipeline Research

**Researched:** 2026-05-30  
**Purpose:** Understand the full landscape of Australian residential architectural document types, their conventions, and what each type means for every stage of the ProCalc AI extraction pipeline.

---

## Contents

1. [Document lifecycle — the three (or four) stages](#1-document-lifecycle)
2. [Document type deep-dive](#2-document-type-deep-dive)
3. [Project types — dwelling typologies](#3-project-types)
4. [Drawing numbering and discipline codes](#4-drawing-numbering)
5. [Scale conventions](#5-scale-conventions)
6. [Area schedule variations](#6-area-schedule-variations)
7. [Impact on each pipeline stage](#7-pipeline-stage-impact)
8. [Summary matrix](#8-summary-matrix)
9. [Key risks and recommendations](#9-key-risks)

---

## 1. Document Lifecycle

An Australian residential project progresses through sequential document stages, each with a distinct purpose, detail level, and regulatory audience.

```
 ┌─────────────────────┐
 │   DA / CDC          │  Planning approval (council or certifier)
 │   (Development      │  Design intent, zoning compliance
 │    Application)     │  High-level, minimal construction detail
 └─────────┬───────────┘
           │ ↓ (DA granted with conditions)
 ┌─────────┴───────────┐
 │   CC                │  Building regulation compliance
 │   (Construction     │  Structural, BCA/NCC, BASIX, engineering
 │    Certificate)     │  Certifier-approved, still not build-ready
 └─────────┬───────────┘
           │ ↓ (CC granted)
 ┌─────────┴───────────┐
 │   IFC / Working     │  Builder's "instruction manual"
 │   Drawings          │  Fully detailed: joinery, schedules, sections
 │   (Issued for       │  Coordinated across all consultants
 │    Construction)    │  Most complete set — our primary target
 └─────────────────────┘
           │ ↓ (construction begins)
 ┌─────────┴───────────┐
 │   Site / Shop       │  Contractor-specific details
 │   Drawings          │  Steel fabricator, cabinet maker, tiling
 │                     │  Not part of architect's set
 └─────────────────────┘
```

**Alternative path (NSW):**

```
 ┌─────────────────────┐
 │   CDC               │  Combined DA + CC (fast-track)
 │   (Complying        │  Only for straightforward projects
 │    Development      │  that fully meet pre-defined codes)
 │    Certificate)     │  Issued by private certifier
 └─────────────────────┘
           │ ↓ (CDC granted → construction)
```

### 1.1 What we already have

| PDF | Document type | Pages | Architect | Notes |
|-----|---------------|-------|-----------|-------|
| `Mesh Reservoir 620k mid.pdf` | **Working drawings (IFC)** | 30 | Mesh Design Projects | Full set: A001–A902, Issue for Construction Rev E |
| `DMP Elm Northcote 750k.pdf` | **Working drawings (IFC)** | 48 | The Makeover Group | Full set with extensive joinery details |
| `200302_461 Canning St_Planning Application Drawings 1.2M.pdf` | **Planning Application (DA)** | 18 | (unknown) | 0 text pages (3 empty scanned), 18 sheets total |

---

## 2. Document Type Deep-Dive

### 2.1 Development Application (DA) / Planning Application

**Purpose:** Obtain planning permission from the local council.

**Typical size:** 10–25 sheets (single dwelling), up to 60+ (multi-unit)

**Common sheet structure:**

| Sheet | Content | Present in our sample? |
|-------|---------|----------------------|
| DA-01 / A001 | Cover sheet, project summary | Yes (p00) |
| DA-02 | Existing conditions / site survey | Yes (p02–p04) |
| DA-03 | Demolition plan | Yes (p03) |
| DA-04 | Proposed site plan (with AREA ANALYSIS) | Yes (p05) |
| DA-05 | Proposed ground floor plan | Likely (p07?) |
| DA-06 | Proposed first floor plan (if 2-storey) | — |
| DA-07 | Proposed elevations | Yes (p08?) |
| DA-08 | Sections | — |
| DA-09 | Shadow diagrams (9am, 12pm, 3pm × 2 seasons) | — |
| DA-10 | Streetscape elevation / context | Yes (p06) |
| DA-11 | Landscape plan | — |
| DA-12 | Stormwater / drainage plan | — |
| — | Notification plan (A4, simplified) | — |

**Key characteristics:**
- **Drawing numbers** often use `DA-` prefix (e.g. `DA-100`, `DA-201`) rather than the standard `A100`
- **Scale:** typically 1:100 for plans, 1:200 for site plans
- **Text layer:** usually excellent (CAD-exported)
- **AREA ANALYSIS table:** almost always present on the proposed site plan, though may use different formatting/labels than working drawings
- **Schedules:** door/window schedules are basic or absent
- **Engineering:** rarely included (civil/structural comes at CC stage)
- **Mixed content:** report pages (SEE, BASIX, waste management) may be appended as separate pages — these are NOT CAD drawings and may have poor or no text layer
- **Sheet count:** lower than working drawings (typically 10–25 vs 30–50)

**What's NOT typically in a DA set:**
- Detailed joinery elevations
- Reflected ceiling plans (RCP)
- Electrical plans
- Comprehensive door/window schedules
- Structural framing plans
- Section details at 1:10 or 1:5

**Our DA sample (`200302_461 Canning St`):**
- 18 pages, but 3 have **zero text** (p11, p12, p13 — likely scanned images/renders)
- All other pages have **~900–2,400 chars** (consistent with CAD-exported text)
- Uses the project number `1811` as its primary identifier, not A### drawing numbers
- Has existing conditions, demolition, site plan, elevations, shadow diagrams
- No room labels visible from first-line scan (unlikely to have a full rooms layout)

### 2.2 Construction Certificate (CC)

**Purpose:** Satisfy BCA/NCC compliance and receive permission to construct.

**Typical size:** 20–40 sheets

**What it adds beyond DA:**
- Structural engineering plans (footings, slabs, framing, bracing)
- Hydraulic/plumbing plans
- BASIX compliance documentation (NSW)
- Updated plans reflecting all DA consent conditions
- Energy efficiency certification (NatHERS)
- More detailed sections and construction notes
- Fire safety and waterproofing details

**Key characteristics:**
- **Drawing numbers** often use `CC-` prefix (e.g. `CC-100`, `CC-201`)
- **Scale:** same as DA (1:100, 1:200)
- **Engineering sheets:** structural framing plans use `S` prefix (S001, S100)
- **Text layer:** CAD-exported, usually excellent
- **No joinery detail** — that comes at IFC stage
- **Still has AREA ANALYSIS** on the site plan (mostly unchanged from DA)
- **Still has room labels** on floor plans (but may be less finalised)

**What the pipeline would encounter:**
- A CC set looks very similar to a working drawing set in terms of classification classes — both have site plans, floor plans, elevations, sections
- The key difference is the ABSENCE of joinery_detail pages and the PRESENCE of engineering sheets (structural plans)
- AREA ANALYSIS and room labels are present just as in working drawings
- Schedules may be present but less comprehensive

### 2.3 Complying Development Certificate (CDC)

**Purpose:** Fast-track combined planning + building approval (NSW only, under State Environmental Planning Policy).

**Typical size:** 15–30 sheets

**Key characteristics:**
- Same general structure as DA but with more building detail included
- Issued by a private certifier, not council
- Drawing numbers: often standard A### (since the architect is producing a full set)
- Site plan with AREA ANALYSIS is still present
- Eligible projects: straightforward detached houses, small extensions only

**Pipeline impact:** CDC sets behave similarly to DA sets but are closer to working drawings in completeness. The existing pipeline should handle them without changes beyond what's needed for DA.

### 2.4 Working Drawings / IFC (Issued for Construction) — THE PRIMARY TARGET

**Purpose:** Guide the builder and trades during construction.

**Typical size:** 25–60+ sheets

**What it includes (everything a builder needs):**
- All the sheets from DA + CC
- **Joinery details** (kitchen, bathroom, WIR cabinetry at 1:5–1:20)
- **Window and door schedules** (comprehensive: size, type, frame, glass, hardware)
- **Reflected ceiling plans** (RCP with lighting, cornices, bulkheads)
- **Electrical plans** (power points, switches, data, comms)
- **Finishes schedules** (floor, wall, ceiling materials per room)
- **Fully coordinated sections** (roof-wall-footing junctions at 1:10–1:5)
- **Consultant coordination** (structural, hydraulic, civil overlays)

**Key characteristics:**
- **Drawing numbers:** standard A### series (A001–A999)
- **Discipline prefixes:** S (structural), E (electrical), H (hydraulic), L (landscape)
- **Scale:** 1:100 for plans, 1:50–1:20 for details, 1:10–1:5 for junctions
- **Text layer:** CAD-exported, highest quality
- **Room labels:** consistent, full set on all floor plans
- **AREA ANALYSIS:** still present on the site plan (usually unchanged from CC stage)
- **Construction status:** title block says "ISSUE FOR CONSTRUCTION" or "IFC" or "CC"
- **Revision tracking:** often has amendment bubbles and revision block

**This is what the pipeline was designed for.** Both Mesh and DMP are working drawings.

### 2.5 Shop / Site Drawings (not in scope, informational)

**Purpose:** Contractor-specific fabrication and installation.

**Examples:** Steel fabricator shop drawings, cabinet maker shop drawings, tile layout, waterproofing details.

**Key characteristics:**
- Produced by subcontractors, not the architect
- Not part of the main architectural set
- Different drawing standards (may not follow AS 1100.301)
- Often have poor or no text layer (scanned or image-based)
- Likely to be irrelevant or general_notes

---

## 3. Project Types

The pipeline currently assumes a **single-detached dwelling** (Class 1a). But Australian residential projects span several typologies, each with implications.

### 3.1 NCC Building Classifications

| Class | Description | Example | Count of samples |
|-------|-------------|---------|-----------------|
| **Class 1a** | Single dwelling (detached house, terrace, townhouse) | Mesh, DMP | 2 |
| **Class 1b** | Small boarding/guest house | B&B, hostel | 0 |
| **Class 2** | Multi-dwelling building (units stacked) | Apartments, flats | 0 |

For architectural plans, the key practical distinction is:

| Project type | NCC Class | ProCalc pipeline fit |
|--------------|-----------|---------------------|
| Single detached house | 1a | ✅ **Current target** — single site plan, single GF plan |
| Duplex (two side-by-side dwellings) | 1a | ⚠️ One site plan but TWO ground floor plans — `proposed_plan_primary` count would be 2 |
| Townhouse / Terrace (3+ attached) | 1a | ⚠️ Same issue — multiple floor plans, one site plan |
| Villa development (5+ units) | 1a | ❌ Many floor plans, landscape plan, common areas |
| Apartment building (2+ stacked units) | 2 | ❌ Multiple floors, common property, different area conventions |
| Mixed-use (retail + residential) | 2+5+7 | ❌ Way beyond current scope |

**Implication for "ground floor":** Duplex/townhouse plans show TWO or MORE dwelling floor plans on the same A201 sheet (or adjacent sheets). The current `proposed_plan_primary` → single `rooms_data` and single `geometry_data` assumption breaks.

### 3.2 How different project types affect the pipeline

| Project type | Site plan | Floor plans | Room extraction | Geometry |
|-------------|-----------|-------------|-----------------|----------|
| **Single detached** | 1 AREA ANALYSIS | 1 GF (maybe 1 FF) | 1 set of rooms | 1 building outline |
| **Duplex** | 1 AREA ANALYSIS (site) + potentially 2× dwelling areas | 2 GFs or 1 sheet showing both | 2 room sets → conflated | 2 building footprints on one page |
| **Townhouse (3–4)** | 1 AREA ANALYSIS | 3–4 GFs across 2+ sheets | 3–4 room sets | 3–4 footprints |
| **Apartment** | Site plan (different area convention) | 1 ground floor + typical floor + upper floors | Per-floor room inventories | Large building, many wall lines |
| **Alteration/Extension** | 1 AREA ANALYSIS | Existing + proposed plans | Room labels show existing vs new | Some walls hatched "existing", some "new" |

### 3.3 The "existing vs proposed" distinction

Working drawings typically show ONLY the proposed building on the floor plan. But DA sets often include:
- **Existing** floor plans (pre-renovation)
- **Proposed** floor plans (post-renovation / new build)

These map to:
- Existing → `existing_plan`
- Proposed → `proposed_plan_primary` or `proposed_plan_ff`

Stage 3 (rooms) and Stage 4 (geometry) currently ONLY process `proposed_plan_primary`. This is correct for new builds but misses the context in alteration projects.

---

## 4. Drawing Numbering

### 4.1 Standard Australian Convention (AS 1100.301)

| Prefix | Discipline |
|--------|-----------|
| A | Architectural (main set) |
| C | Civil |
| D | Demolition |
| E | Electrical |
| H | Hydraulic (plumbing) |
| L | Landscape |
| M | Mechanical |
| P | Planning |
| S | Structural |

### 4.2 Sheet Number Series

| Range | Architectural content | Present in which doc type |
|-------|----------------------|--------------------------|
| A000–A099 | Cover sheet, drawing list, project info | All types |
| A100–A199 | Site plans, existing conditions | All types |
| A200–A299 | Floor plans, electrical, RCP | **Working drawings only** (DA: A200 or DA-200) |
| A300–A399 | Elevations | All types |
| A400–A499 | Door/window schedules | Working drawings, some DA |
| A500–A599 | Sections | All types |
| A600–A699 | Construction details | Working drawings only |
| A700–A799 | Joinery details | **Working drawings only** |
| A800–A899 | Shadow diagrams | DA and CDC primarily |
| A900–A999 | Perspectives, renders | DA and CDC primarily |

### 4.3 Variants by document type

| Document type | Drawing number format | Example | In text layer? |
|---------------|----------------------|---------|----------------|
| Working drawings (IFC) | A### | A100, A201 | ✅ Usually |
| Development Application | DA-### | DA-100, DA-201 | ✅ Always |
| Construction Certificate | CC-### | CC-100, CC-201 | ✅ Always |
| CDC (NSW) | A### | A100, A201 | ✅ Usually |
| Project-specific | e.g. MP-### | MP-01, MP-100 | ✅ Always |

### 4.4 What this means for the pipeline

Current `DRAWING_NO_RE` in `01_classification.py`:
```
\b([ACDEFHLMPS])[ \t]*\d{3}[a-zA-Z]?\b
```

Only matches the A### format. DA/CC/CDC sets with `DA-` or `CC-` prefixes will return `None` from the regex fallback. **This is acceptable** because the LLM is the primary source for drawing numbers and can handle any format. The regex is only a fallback.

However, adding DA/CC/SK/DP prefix patterns to the regex (as recommended in CLASSIFY_FIX_REPORT.md) would give better coverage on planning application PDFs.

---

## 5. Scale Conventions

### 5.1 Standard scales by drawing type

| Drawing type | Typical scale | Document type |
|-------------|---------------|---------------|
| Context / locality plan | **1:1000, 1:2500, 1:5000** | DA (site analysis) |
| Site plan (standard) | 1:200, 1:100 | All |
| Floor plan | 1:100 | All |
| Elevation | 1:100, 1:50 | All |
| Section | 1:100, 1:50 | All |
| Detail section | 1:20, 1:10 | Working drawings |
| Joinery elevation | 1:20, 1:5 | Working drawings |
| Component detail | 1:5, 1:2, 1:1 | Working drawings |
| Shadow diagram | 1:200, 1:100 | DA, CDC |

### 5.2 Missing scale denominators

Current `VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500}`

**Missing and needed for planning applications:**
- **1000** — context/site analysis plans (very common in DA sets)
- **2500** — masterplans, locality plans
- **5000** — regional context

### 5.3 Compound scales

Some sections show "1:100/1:10" (overall section at 1:100, detail at 1:10). The current regex captures "1:100" but misses the "/1:10" part. The LLM handles this fine in its reasoning.

---

## 6. Area Schedule Variations

### 6.1 The AREA ANALYSIS table

The AREA ANALYSIS table on the site plan is the primary source for area values. Its format varies:

| Field | Typical label variants | Present in which doc type |
|-------|----------------------|--------------------------|
| Site area | Site Area, Site/Lot Area, Total Site Area | All |
| Dwelling area | Proposed Dwelling, Dwelling, Building Area, Ground Floor, GFA | All |
| First floor | First Floor, Upper Floor | Multi-storey only |
| Porch | Porch, Covered Porch, Portico | Usually |
| Outdoor living | Outdoor Living, Alfresco, Deck, Covered Outdoor | Often |
| Site coverage % | Site Coverage, Coverage, Site Cover % | All |
| Site coverage m² | Site Coverage (m²), Coverage Area | All |

**Planning application variants:**
- May use different terminology: "TOTAL SITE AREA" instead of "SITE AREA"
- May include **hardscape** area, **landscape** area, **deep soil** zone — fields not in the current schema
- May not have **porch** and **outdoor_living** broken out separately (lumped into "dwelling")
- Site coverage formula is always the same: `(dwelling + porch + outdoor_living) / site_area`

### 6.2 What is NOT in a planning application's AREA ANALYSIS

DA sets often lack the A220 lighting calculation table (used in Mesh as a cross-check). The lighting dwelling values (188.48 m²) only appear on the RCP in working drawings — DA sets typically don't have RCPs.

### 6.3 Multi-dwelling area schedules

For duplex/townhouse projects, the area schedule may list:
- Lot/site area (total)
- Unit 1 dwelling area
- Unit 2 dwelling area
- Common areas
- Total site coverage

The current schema (`site_area`, `ground_floor`, `first_floor`, `porch`, `outdoor_living`) assumes single-dwelling. A unit-specific field doesn't exist.

---

## 7. Pipeline Stage Impact

### 7.1 Stage 1 — Classification

**Current status:** The prompt is working-drawings-centric ("The document is a CAD-exported PDF. Each page has a title block..."). It needs to handle:

| Document type | What changes | Risk |
|---------------|-------------|------|
| Working drawings | Current prompt works perfectly | None |
| **Planning application (DA)** | Report pages mixed with drawings; DA-### prefixes; landscape/stormwater plans; scanned pages | **Medium** — needs prompt update + new classes |
| **Construction certificate (CC)** | Very similar to working drawings; CC-### prefix; engineering sheets | Low — minor prompt adjustment |
| **CDC** | Similar to DA but faster path; often A### numbering | Low |

**Specific issues by document type:**

**DA-specific classification challenges:**
1. **Report pages** — SEE, BASIX, waste management plans are text documents mixed between CAD drawings. Current classes have no explicit guidance → they fall into `general_notes` (works, but not designed for it).
2. **Scanned pages** — 3 pages in our DA sample have 0 bytes of text. These should be `irrelevant`.
3. **Landscape plans** — DA often includes dedicated landscape plans. No `landscape_plan` class currently.
4. **Stormwater/drainage plans** — Common in DA. No `stormwater_plan` class.
5. **DA-### drawing numbers** — Standard A### regex won't match. LLM handles it but regex fallback returns null.
6. **Notification plan** — A simplified A4 page with site plan + elevations for neighbour notification. Could be classified as `site_plan` or `existing_plan` — neither is ideal.
7. **Shadow diagrams in quantity** — DA sets often have 8+ shadow diagrams (4 times × 2 seasons). Current class handles this, but they're not always in the A800 range.

**CC-specific issues:**
1. **Structural engineering drawings** — S-prefixed drawings (S001, S100) are structurally-focused. Should these be a new `engineering_plan` class?
2. **Hydraulic/civil drawings** — H-prefixed or C-prefixed. Same question.
3. **No shadow diagrams** — Already done at DA stage, not repeated.
4. **No perspectives** — Not needed for CC.
5. **More sections** — CC often adds structural sections not in DA.

**Classification classes needed for planning applications (beyond current 18):**

| New class | Why | In which doc type |
|-----------|-----|-------------------|
| `landscape_plan` | Dedicated landscape/planting plans | DA, CDC |
| `stormwater_plan` | Drainage/detention plans | DA, CC, CDC |
| `engineering_plan` | Structural/civil/hydraulic engineer drawings | CC, working drawings |

### 7.2 Stage 2 — Areas

**Impact by document type:**

| Document type | Area table present? | Risk level |
|---------------|--------------------|------------|
| Working drawings | ✅ Yes, fully formatted | None |
| DA | ✅ Yes, but may use different labels | **Low** — Flash handles label variants |
| CC | ✅ Yes, same as DA | None |
| CDC | ✅ Yes, same as DA | None |

**Key differences in DA area tables:**
- May use "TOTAL SITE AREA" vs "SITE AREA"
- May include landscape area, deep soil, hardscape — fields not in schema (Flash would return null for those)
- Site coverage % — some DA sets omit this and only show the m² value
- May combine dwelling + porch + outdoor_living into a single "TOTAL BUILDING COVERAGE" (Flash must infer the split)
- Status field: "planning_application" (already supported in `_STATUS_MAP`)

**Potential pipeline failure:** If the DA set's area table uses significantly different formatting or label names that confuse Flash. The prompt says: "If a field is not present, return null and explain why." This is robust. Flash is the right tool for this stage — the old Python parser would have failed on any formatting variation.

### 7.3 Stage 3 — Rooms

**Impact by document type:**

| Document type | Room labels present? | Risk level |
|---------------|--------------------|------------|
| Working drawings | ✅ Yes, at canonical font size | None |
| DA | ✅ Usually present but potentially less detailed | **Medium** |
| CC | ✅ Yes (construction-ready) | Low |

**DA-specific room extraction challenges:**

1. **Less detail in DA floor plans** — DA floor plans may show only room names without door numbers, window tags, or dimension strings. This is actually **good** for room extraction — less noise to filter.

2. **Room naming may differ** — DA sets may use more generic names ("BEDROOM 1" vs "Bed 01", "MEALS" vs "Dining"). The prompt already includes both variants.

3. **Font size cluster may differ** — In DA sets, if there are fewer annotation layers (no dimensions, no door tags), the font size gap between room labels and everything else may be larger, making extraction easier.

4. **Existing floor plans** — DA shows existing floor plans alongside proposed. The current pipeline only processes `proposed_plan_primary`, which is correct for room extraction.

5. **Multi-dwelling trickiness** — Duplex/townhouse DA may show 2+ dwellings on one floor plan sheet. Room extraction would conflate both dwellings into one room inventory. **This is a known gap.**

6. **Less consistent formatting** — DA sets are often produced in a hurry with less CAD standardisation. Text layers may be messier.

**What the current rooms prompt handles well:**
- Relative font size language ("second-largest cluster") — works across all CAD-exported PDFs
- Room type mapping (28+ label variants across 17 types) — tested on Mesh and DMP
- Slash-separated combined labels — explicitly excluded
- Adjacent span merging ("Outdoor" + "Living" → "Outdoor Living")
- Legend/annotation ignoring

### 7.4 Stage 4 — Geometry

**Impact by document type:**

| Document type | Walls as vector paths? | Risk level |
|---------------|----------------------|------------|
| Working drawings | ✅ Yes — CAD export with dark strokes | None |
| DA | ✅ Usually yes — same CAD source | Low |
| CC | ✅ Yes | None |

**DA-specific geometry challenges:**

1. **Stroke width consistency** — If the DA was exported from a different CAD setup than the working drawings, stroke widths could differ. The 0.45pt threshold might not apply.

2. **Existing vs proposed walls** — DA plans sometimes show existing walls with a different line weight or hatching. Filter D (dark, ≥0.45pt, ≥15pt) would pick up ALL dark walls regardless of existing/proposed status. This could over-count walls.

3. **Plan bounds** — The 40pt margin excluding title block assumes the title block is at the page edge. DA sets sometimes have larger margins or different title block positioning.

4. **Scale calibration** — DA sets may not have an overall dimension like "20490" on the floor plan. Our DMP sample already has this problem (`GT_OVERALL_MM` is None). For DA sets without a full-span dimension, calibration relies on the nominal 35.28 mm/pt or Flash finding a dimension string. DMP's calibration produced 50% error because Flash picked up a room dimension (2340) instead of the overall length.

5. **Multi-dwelling geometry** — Two building footprints on one page → wall extraction would return walls from BOTH dwellings, merged.

### 7.5 Stage 5 — Validation

**Impact by document type:**

| Document type | Ground truth available? | Risk level |
|---------------|------------------------|------------|
| Working drawings | ✅ Yes (hardcoded for Mesh and DMP) | None |
| DA / CC | ⚠️ Only if we add to `_GROUND_TRUTHS` | **Medium** |
| New untested PDF | ❌ No ground truth → validation skips all checks | Low (skips gracefully) |

**Key issues:**

1. **A220 cross-check missing** — DA sets don't have RCPs (A220), so the lighting dwelling cross-check (188.48 vs 198.07) is unavailable. The validation currently handles this via `if GT_LIGHTING_DWELLING is None: skip`.

2. **Room count validation** — For DA sets without `expected_rooms`, the room check is skipped. This is handled.

3. **Calibration error threshold** — 5% threshold works for Mesh (0.96% error). For DMP (50% error with calibration), it correctly flags. For untested PDFs, the threshold may need to be widened or calibration method improved.

### 7.6 Stage 6 — SVG Render

**Impact by document type:**

| Document type | Wall geometry quality | Render path | Risk |
|---------------|----------------------|-------------|------|
| Working drawings | 131 walls (Mesh), good quality | Primary (wall lines) | None |
| DA | Unknown — could have fewer walls | Primary or fallback | **Low-Medium** |
| CC | Similar to working drawings | Primary (wall lines) | Low |

**Potential issues:**
- DA sets with fewer wall lines (less detailed plans) < 20 walls → fallback to centroid render
- Multi-dwelling plans with 2+ building footprints → SVG shows combined geometry
- DA elevations/shadow diagrams → not rendered by current pipeline (only processes `proposed_plan_primary`)

---

## 8. Summary Matrix

| Aspect | Working Drawings (IFC) | Development Application (DA) | Construction Certificate (CC) | Complying Development (CDC) |
|--------|----------------------|------------------------------|-------------------------------|----------------------------|
| **Purpose** | Build the house | Get planning approval | Get building compliance sign-off | Fast-track combined approval (NSW) |
| **Typical pages** | 25–60 | 10–25 | 20–40 | 15–30 |
| **Text layer** | ✅ Excellent | ✅ Good (some scanned pages) | ✅ Excellent | ✅ Good |
| **Drawing numbers** | A### | DA-### | CC-### or A### | A### |
| **AREA ANALYSIS** | ✅ Yes | ✅ Yes (different labels possible) | ✅ Yes | ✅ Yes |
| **Room labels** | ✅ Full set | ✅ Present, less detail | ✅ Full set | ✅ Full set |
| **Wall geometry** | ✅ CAD-exported | ✅ CAD-exported | ✅ CAD-exported | ✅ CAD-exported |
| **Joinery details** | ✅ Yes (many pages) | ❌ No | ❌ No | ❌ No |
| **Engineering sheets** | ✅ Yes | ❌ No | ✅ Yes | ⚠️ Sometimes |
| **Landscape plan** | ⚠️ Sometimes | ✅ Often | ⚠️ Sometimes | ⚠️ Sometimes |
| **Shadow diagrams** | ✅ Sometimes | ✅ Yes (many) | ❌ No | ❌ No |
| **Scanned/report pages** | ❌ Rare | ✅ Yes (SEE, BASIX) | ⚠️ Rare | ⚠️ Few |
| **Pipeline fit** | **🟢 Perfect** | **🟡 Good** — needs prompt updates + new classes | **🟢 Good** — minor changes needed | **🟢 Good** — minor changes |

---

## 9. Key Risks and Recommendations

### 9.1 Immediate actions (low effort, high value)

| # | Action | Affects | Risk |
|---|--------|---------|------|
| 1 | Add `landscape_plan`, `stormwater_plan`, `engineering_plan` to `VALID_CLASSES` in `01_classification.py` | Stage 1 | Low — additive only |
| 2 | Add `1000`, `2500`, `5000` to `VALID_SCALE_DENOMS` in `01_classification.py` | Stage 1 regex fallback | Low |
| 3 | Extend `DRAWING_NO_RE` to match `DA-###`, `CC-###`, `SK-##` prefixes | Stage 1 regex fallback | Low |
| 4 | Update classification prompt to describe planning applications as a possible input type | Stage 1 prompt | Medium — must not regress working drawings |
| 5 | Add page-count mismatch and useful-class-count checks to `01_classification.py` | Stage 1 validation | Low |

### 9.2 Medium-term risks

| # | Risk | When it bites | Mitigation |
|---|------|-------------|------------|
| 1 | **Multi-dwelling floor plans** — duplex/townhouse shows 2+ dwellings on one sheet → room extraction conflates them | Next duplex/townhouse PDF | Pipeline needs per-dwelling room and geometry segmentation |
| 2 | **DA sets without overall dimension** — calibration fails (as seen with DMP) | Every DA/CC set without a 20490-style dimension | Better calibration heuristic: find the dimension string that spans the plan bounds, or use known room widths |
| 3 | **DA sets without AREA ANALYSIS table** — some small DA submissions use a separate spreadsheet | Rare but possible | Validate at pipeline level: if stage 2 returns null for all fields, stop and flag |
| 4 | **Scanned DA pages in the middle of CAD pages** — text layer is empty but the LLM receives an empty string | Likely in our DA sample (3 empty pages) | Already handled — empty pages → `irrelevant` via the prompt update |
| 5 | **Batch processing** — running the pipeline across 100+ PDFs means ground truth must be entered for each | First large-scale test | Make ground truth optional; validation reports "no ground truth available" rather than "skip" |

### 9.3 Long-term architectural challenges

| # | Challenge | Impact | When relevant |
|---|-----------|--------|-------------|
| 1 | **Apartment buildings (Class 2)** — different area conventions, unit schedules, common property | Pipeline rearchitecture needed | When we get our first apartment PDF |
| 2 | **Existing + proposed overlay plans** — alteration projects show both on the same sheet, walls may be hatched | Geometry extraction would need to distinguish existing (dashed) from proposed (solid) walls | When we get an alteration/extension project |
| 3 | **Non-100 scales** — 1:50 floor plans (common for small bathrooms/kitchens), 1:500 site plans | mm_per_pt constant would need scale-based adjustment | Should already work since mm_per_pt = `25.4/72 × scale_denominator` but scale must be detected per-page |
| 4 | **Survey-strata / subdivided lot plans** — the site plan may show only a portion of the original lot | Site area may be the subdivided area, not the original | Need to flag this in validation |

### 9.4 What each document type tells us about stage behaviour

| Document type | Stage 1 | Stage 2 | Stage 3 | Stage 4 | Stage 5 | Stage 6 |
|---------------|---------|---------|---------|---------|---------|---------|
| **Working drawings** | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 100% | ✅ 100% |
| **DA / Planning App** | 🟡 New classes needed | 🟡 Different labels, Flash handles it | 🟡 Less noise, still works | 🟡 Calibration risk, threshold risk | 🟡 No GT for DA → most checks skip | 🟡 Fewer walls → may hit centroid fallback |
| **CC** | 🟡 Engineering sheets = new class | ✅ Same as working drawings | ✅ Same as working drawings | ✅ Same as working drawings | 🟡 May have same calibration gaps | ✅ Should produce good SVG |
| **CDC** | 🟡 Similar to DA but A### numbering | ✅ Similar to working drawings | ✅ Similar to working drawings | ✅ Same risk as DA | 🟡 No GT → most checks skip | ✅ Should produce good SVG |

---

## Appendix A: Our DA Sample — First Look

`200302_461 Canning St_Planning Application Drawings 1.2M.pdf`

| Page | Chars | Content |
|------|-------|---------|
| p00 | 1,628 | Cover — "PLANNING APPLICATION" + project 1811 |
| p01 | 1,009 | General notes or location plan |
| p02 | 2,441 | Existing site — paling fence, trees |
| p03 | 1,661 | Demolition plan — existing carport |
| p04 | 1,892 | Existing front facade / room facade |
| p05 | 1,851 | Site plan — ridge heights, levels |
| p06 | 1,607 | Streetscape context / existing front side |
| p07 | 2,294 | Proposed elevation — timber, windows |
| p08 | 1,770 | Proposed — private raised garden |
| p09 | 1,840 | Skylight roof / roof plan |
| p10 | 940 | Planning application cover repeat |
| p11 | **0** | ❌ Empty (scanned image?) |
| p12 | **0** | ❌ Empty (scanned image?) |
| p13 | **0** | ❌ Empty (scanned image?) |
| p14 | 1,058 | Planning application page (notes?) |
| p15 | 1,162 | Shadow diagram — 22 SEPTEMBER 12:00 |
| p16 | 1,098 | Existing elevation/context |
| p17 | 1,257 | Planning application (cover repeat?) |

**Notable:** 3 fully blank pages (p11–p13), no floor plan with room labels visible from text head, uses "1811" as project number not A### drawing numbers.

---

## Appendix B: Quick Reference — Scale Denominators Needed

```python
# Working drawings only
VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500}

# For planning applications too
VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2500, 5000}
```

## Appendix C: Quick Reference — Drawing Number Regex

```python
# Current (A### only)
DRAWING_NO_RE = re.compile(r'\b([ACDEFHLMPS])[ \t]*\d{3}[a-zA-Z]?\b')

# Extended for planning applications
DRAWING_NO_RE = re.compile(
    r'\b(?:DA|CC|SK|DP)[-\s]*\d{2,4}[A-Za-z]?\b'
    r'|\b([ACDEFHLMPS])[ \t]*\d{3}[a-zA-Z]?\b'
)
```

## Appendix D: Quick Reference — Classification Classes by Document Type

| Class | Working Dwgs | DA | CC | CDC |
|-------|-------------|-----|-----|-----|
| title_sheet | ✅ | ✅ | ✅ | ✅ |
| general_notes | ✅ | ✅ | ✅ | ✅ |
| site_plan | ✅ | ✅ | ✅ | ✅ |
| existing_plan | ✅ | ✅ | ✅ | ✅ |
| proposed_plan_primary | ✅ | ✅ | ✅ | ✅ |
| proposed_plan_ff | ✅ | ✅ | ✅ | ✅ |
| proposed_plan_supplementary | ✅ | ✅ | ✅ | ✅ |
| **landscape_plan** | — | ✅ | — | ✅ |
| **stormwater_plan** | — | ✅ | ✅ | — |
| **engineering_plan** | ✅ | — | ✅ | — |
| electrical_plan | ✅ | — | — | — |
| rcp | ✅ | — | — | — |
| roof_plan | ✅ | ✅ | ✅ | ✅ |
| elevations | ✅ | ✅ | ✅ | ✅ |
| sections | ✅ | ✅ | ✅ | ✅ |
| door_schedule | ✅ | — | — | — |
| window_schedule | ✅ | — | — | — |
| joinery_detail | ✅ | — | — | — |
| shadow_diagram | ✅ | ✅ | — | — |
| perspective | ✅ | ✅ | — | — |
| irrelevant | ✅ | ✅ | ✅ | ✅ |

---

## Appendix E: Prompt Strategy by Stage

| Stage | Current prompt target | Needs to also handle | Main change |
|-------|-----------------------|---------------------|-------------|
| 1 — Classify | "working drawing set" | "planning application documents" | Add planning language, new classes, report/scanned guidance |
| 2 — Areas | "Site Plan / Area Analysis page (A100)" | Same area table but may use different labels | Map table column labels (Flash handles it) |
| 3 — Rooms | "A201 — Proposed Ground Floor Plan" | Same structure, potentially less noise | Possibly update room type map for DA naming variants |
| 4 — Geometry | No prompt (pure code) | No change | Code-only: possibly lower stroke threshold |
| 5 — Validate | Flash narrative checks ground truth | No ground truth = graceful skip | Already handled |

---

*End of research document.*

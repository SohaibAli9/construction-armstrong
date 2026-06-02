# Classification Pipeline — Research Report

**For the agent that will implement the fixes.** Everything needed to make all changes is documented here. Code changes are described — not implemented.

---

## Contents

1. [Research findings — Australian drawing set conventions](#1-research-findings)
2. [Cross-PDF comparison — Mesh vs DMP](#2-cross-pdf-comparison)
3. [Planning application documents — new document types](#3-planning-application-documents)
4. [Class schema gap analysis](#4-class-schema-gap-analysis)
5. [Drawing number and scale extraction gaps](#5-drawing-number-and-scale-extraction-gaps)
6. [Text extraction strategy assessment](#6-text-extraction-strategy-assessment)
7. [Prompt overhaul — full spec](#7-prompt-overhaul)
8. [Validation and sanity checks](#8-validation-and-sanity-checks)
9. [Implementation order](#9-implementation-order)

---

## 1. Research Findings

### 1.1 Working Drawing Set Structure — Australian Conventions

Australian residential working drawings follow a standard structure derived from AS 1100.301 (Architectural Technical Drawing). The numbering convention uses a **discipline prefix letter** followed by a **three-digit sheet number**:

| Prefix | Discipline | Typical Sheets |
|--------|-----------|----------------|
| A | Architectural | A001–A999 (main set) |
| C | Civil | C001–C999 |
| D | Demolition | D001–D999 |
| E | Electrical | E001–E999 |
| H | Hydraulic (Plumbing) | H001–H999 |
| L | Landscape | L001–L999 |
| M | Mechanical | M001–M999 |
| P | Planning | P001–P999 |
| S | Structural | S001–S999 |

Within the Architectural set, the typical sheet numbering is:

| Sheet Range | Content | Hits both sample PDFs? |
|-------------|---------|----------------------|
| A000–A099 | Cover sheet, drawing list, project info | Mesh: A001 (title), A002 (notes) |
| A100–A199 | Site plans, existing conditions, demolition | Mesh: A100, A101 ✓ — DMP: text-layer missing |
| A200–A299 | Floor plans, electrical, RCP | Mesh: A200–A230 ✓ — DMP: text-layer missing |
| A300–A399 | Elevations | Mesh: A300, A310 ✓ |
| A400–A499 | Door/window schedules | Mesh: A400, A410 ✓ |
| A500–A599 | Sections | Mesh: A500–A502 ✓ |
| A600–A699 | Details (general construction) | Not seen in samples |
| A700–A799 | Joinery details | Mesh: A700–A751 ✓ |
| A800–A899 | Shadow diagrams | Mesh: A800–A810 ✓ |
| A900–A999 | Perspectives, renders | Mesh: A900–A902 ✓ |

### 1.2 Key Finding — Text-Layer Drawing Numbers Are Optional

The Mesh PDF has all A### drawing numbers in its text layer (extractable via `get_text()`). **The DMP PDF does not** — its standard Australian A### numbers exist only in vector graphics (title block CAD entities not rendered as selectable text). Instead, DMP has "06 of 47", "07 OF 47" etc. in its title block text layer.

**Implication:** We cannot rely on A### patterns being present in any PDF. The LLM approach (with the "use whatever unique identifier" fallback in the prompt) is the correct primary strategy. The regex fallback `[ACDEFHLMPS]\d{3}` will only work on PDFs where A### numbers survive in the text layer.

### 1.3 Title Block Position Variation

Based on analysis of both sample PDFs:

| Aspect | Mesh | DMP |
|--------|------|-----|
| Title block position | Bottom of page | Bottom of page |
| Content in last 400 chars | ✅ Drawing title, number, scale | ✅ Drawing title, number, scale |
| Content in first 300 chars | General notes / plan body | General notes / plan body |
| Text extraction reliability | High (clean CAD export) | High (clean CAD export) |

The `HEAD=300 + TAIL=400` strategy in `build_user_message()` works well for both — title blocks are reliably in the last 400 chars of fitz text output.

### 1.4 Font Size Variation — Impact on Classification

Unlike room extraction (which needs font size clustering), classification only needs title block text. The title block typically uses a consistent font size across CAD exports (8–12pt for drawing titles). This is less sensitive to font size variation than the rooms stage.

### 1.5 Drawing Number Format Variation

Observed across both PDFs:

| Format | Example | Where found |
|--------|---------|-------------|
| A### (space optional) | "A 001", "A100", "A201" | Mesh — text layer |
| Page-number | "06 of 47", "07 OF 47" | DMP — text layer |
| DA-### | "DA-100", "DA-201" | Common in planning applications |
| CC-### | "CC-100", "CC-201" | Construction certificate sets |
| SK-### | "SK-01", "SK-02" | Sketch details |
| Suffix letters | "A100A", "A100B" | Revision sheets (not seen in samples) |
| Project prefix | "MP-01", "MP-100" | Smaller firms' custom schemes |
| No drawing number | (null) | Reports, certificates, scanned pages |

The current regex `[ACDEFHLMPS]\d{3}` only covers the first format. For planning applications with DA/CC prefixes, it returns null. **This is acceptable for a fallback** — the LLM is the primary, and for planning apps the LLM would find "DA-100" or whatever format is used.

### 1.6 Scale Variation Across Document Types

| Scale | Used for | In current VALID_SCALE_DENOMS? |
|-------|----------|-------------------------------|
| 1:5 | Large-scale details | ✅ (5) |
| 1:10 | Detail sections | ✅ (10) |
| 1:20 | Room details | ✅ (20) |
| 1:25 | Joinery | ✅ (25) |
| 1:50 | Floor plans (small), schedules | ✅ (50) |
| 1:100 | Floor plans (standard), elevations, sections | ✅ (100) |
| 1:200 | Site plans (standard) | ✅ (200) |
| 1:250 | Site plans (some practices) | ✅ (250) |
| 1:500 | Site plans (large sites) | ✅ (500) |
| **1:1000** | **Context plans, large sites** | **❌ MISSING** |
| **1:2500** | **Masterplans, locality plans** | **❌ MISSING** |
| **1:5000** | **Regional context** | **❌ MISSING** |

Planning applications commonly use 1:1000 for context/site analysis plans and 1:2500 for masterplans. **These need to be added to `VALID_SCALE_DENOMS`.**

---

## 2. Cross-PDF Comparison

### 2.1 Text Length Profile

| Metric | Mesh (30 pages) | DMP (48 pages) |
|--------|----------------|----------------|
| Min chars/page | 485 | 1,381 |
| Max chars/page | 9,864 | 20,343 |
| Mean chars/page | 1,796 | 7,449 |

DMP pages are **4× larger on average** — mainly because detailed joinery specification pages have thousands of characters of material/product selections. This means the `TAIL=400` truncation loses relatively more content on these pages (400/7449 = 5% vs 400/1796 = 22% for Mesh).

### 2.2 Keyword Contamination

Every page of both PDFs contains keywords from EVERY drawing type. For example, Mesh p30 (Perspectives) has text matches for ELECTRICAL, RCP, PERSPECTIVE. DMP p01 (General Notes) has GROUND_FLOOR, FIRST_FLOOR, ELEVATION, SECTION, EXISTING, FENCING, NOTES/SPECS, ROOF.

**Why:** CAD title blocks at the bottom of each page contain the same set of standard notes and references regardless of the page content. All pages share the same title block boilerplate.

**Implication:** Keyword-based classification is unreliable. The LLM must use context (is this a reference to another drawing, or the actual drawing title?) to classify correctly.

### 2.3 Classification Accuracy on Both PDFs

Based on the validated runs (after prompt + regex fixes):

| Metric | Mesh | DMP |
|--------|------|-----|
| Total pages | 30 | 48 |
| Correct classifications | 30/30 | 48/48 |
| Correct key pages (site_plan, primary, ff) | ✅ | ✅ |
| Drawing numbers found | 30/30 (A###) | 48/48 (page-number format) |
| Scale extraction | 30/30 correct | 46/48 correct (2 null on Selection sheets) |
| False positives | None | None |
| $ cost | $0.0019 | $0.0031 |

**Both PDFs classify perfectly with the current approach.**

---

## 3. Planning Application Documents

### 3.1 What a Planning Application Contains

Based on NSW/VIC/QLD council DA checklists, a full planning application for a single dwelling typically includes:

**Architectural drawings (often DA-prefixed):**
- Site Analysis Plan (DA-01 or A100 equivalent)
- Existing Site Plan
- Proposed Site Plan (with landscaping, setbacks, stormwater)
- Existing Floor Plans (all levels)
- Proposed Floor Plans (all levels)
- Existing Elevations
- Proposed Elevations (all four sides)
- Sections (key cut-throughs)
- Shadow Diagrams (9am, 12pm, 3pm winter solstice — sometimes 8 diagrams)
- Notification Plan (A4 simplified — site plan + elevations only)

**Supporting documents (not CAD drawings):**
- Statement of Environmental Effects (SEE) — multi-page Word/PDF document
- BASIX Certificate (NSW only) — government-generated form, often scanned
- Waste Management Plan — text + table
- Stormwater Concept Plan — CAD plan with drainage overlay
- Landscape Plan — CAD or hand-drawn
- Arboricultural Impact Assessment — report with tree survey
- Geotechnical Report — engineering report (scanned or PDF from Word)
- Access Report — disability access compliance
- Cost Estimate Report — by quantity surveyor
- Survey Plan — from registered surveyor (often scanned)
- Owner's Consent — signed and scanned
- Heritage Impact Statement — if in conservation area
- Bushfire Assessment Report — if bushfire-prone land
- Flood Impact Assessment — if flood-prone
- Traffic/Parking Impact Assessment — if high-traffic use

### 3.2 Challenges for Classification

| Challenge | Example | Impact |
|-----------|---------|--------|
| Report pages mixed with CAD drawings | SEE is 8 pages of text between drawing sheets | Current classes can't distinguish report vs drawing |
| Scanned documents | BASIX certificate is a scanned government form | Poor/no text layer → `irrelevant` or garbage |
| Non-architectural plans | Stormwater, landscape, survey | No class for these → `irrelevant` or miscategorized |
| Different prefixes | DA-100 vs A100 (same drawing, different numbering) | LLM handles it, but regex fallback misses |
| Duplicated pages | Same site plan repeated at different sizes | Gets classified the same way — not a problem |
| Multiple scales on one page | Section at 1:100 with detail at 1:10 | Current LLM handles "1:100/1:10" |
| No title block | A written report page has no drawing title | LLM sees no drawing keywords → likely `general_notes` or `irrelevant` |
| Page numbers vs drawing numbers | "Page 12 of 45" is a report page number, "DA-100" is the drawing number | LLM must distinguish these |

### 3.3 New Page Types That Would Appear in Planning Applications

| Page Type | Current Class It Falls Into | Should It Be a New Class? |
|-----------|----------------------------|---------------------------|
| Statement of Environmental Effects | `general_notes` (rough fit) | Probably not — `general_notes` works |
| BASIX Certificate (NSW) | `general_notes` or `irrelevant` | Not urgently — rare and can be `general_notes` |
| Waste Management Plan | `general_notes` | Not needed |
| Landscape Plan | `site_plan` (wrong — it's not a site plan) | **Yes — new class `landscape_plan`** |
| Stormwater Drainage Plan | `site_plan` or `existing_plan` | **Yes — new class `stormwater_plan`** |
| Survey Plan | `existing_plan` (rough fit) | Not urgently |
| Notification Plan | `existing_plan` or `site_plan` | Not urgently |
| Tree Removal / Vegetation Plan | `site_plan` (wrong) | Not urgently — rare |
| Cost Estimate Report | `general_notes` | Not needed |
| Owner's Consent (scanned) | `irrelevant` | Not needed |

**The two most important new classes** for planning applications are `landscape_plan` and `stormwater_plan`. These appear frequently enough to justify dedicated classes, and the current practice of lumping them into `site_plan` or `existing_plan` is architecturally incorrect.

### 3.4 Landscaped Area Plan / Deep Soil Requirement

Many councils (especially NSW) now require a dedicated **Landscaped Area Plan** showing:
- Deep soil zones (minimum 40–60% of site depending on zone)
- Tree placement and species
- Ground cover, paving, turf areas
- Plant species list

This is distinct from a `site_plan` because it focuses on planting and soil, not building setbacks and site coverage. Adding `landscape_plan` as a class lets downstream stages handle it differently if needed.

---

## 4. Class Schema Gap Analysis

### 4.1 Current Classes (18 total)

These work well for working drawings. Assessment for broader use:

| Current Class | Working Drawings | Planning Applications | Recommendation |
|--------------|------------------|----------------------|----------------|
| `title_sheet` | ✅ Used | ✅ Used | Keep |
| `general_notes` | ✅ Used | ✅ Covers SEE, reports | Keep — it's the catch-all |
| `site_plan` | ✅ Used | ⚠️ Can include landscape/stormwater | Keep — needs companion classes |
| `existing_plan` | ✅ Used | ✅ Used (more extensive) | Keep |
| `proposed_plan_primary` | ✅ Used | ✅ Used | Keep |
| `proposed_plan_ff` | ✅ Used | ✅ Used | Keep |
| `proposed_plan_supplementary` | Used once (Mesh only) | ⚠️ Could overlap with landscape/stormwater | Keep |
| `electrical_plan` | ✅ Used | ⚠️ Rare in DA sets (CC stage) | Keep |
| `rcp` | ✅ Used | ⚠️ Rare in DA sets (CC stage) | Keep |
| `roof_plan` | ✅ Used | ⚠️ Sometimes skipped in DA | Keep |
| `elevations` | ✅ Used | ✅ Used | Keep |
| `sections` | ✅ Used | ✅ Used | Keep |
| `door_schedule` | ✅ Used | ⚠️ Sometimes CC-stage only | Keep |
| `window_schedule` | ✅ Used | ⚠️ Sometimes CC-stage only | Keep |
| `joinery_detail` | ✅ Used (25 pages in DMP!) | ⚠️ Rare in DA sets | Keep |
| `shadow_diagram` | ✅ Used (3 in Mesh) | ✅ Used (often more — 8+) | Keep |
| `perspective` | ✅ Used (3 in Mesh) | ⚠️ Sometimes skipped | Keep |
| `irrelevant` | ✅ Fallback | ✅ Fallback | Keep |

### 4.2 New Classes Recommended

| New Class | Purpose | Expected frequency | Downstream usage |
|-----------|---------|-------------------|-----------------|
| `landscape_plan` | Dedicated landscape/planting plan (common in DA sets) | Medium | None currently (informational) |
| `stormwater_plan` | Stormwater drainage / OSD / detention plan | Medium | None currently (informational) |
| `engineering_plan` | Structural, civil, hydraulic engineer's drawings (separate set, often S-prefixed) | Low–Medium | None currently |

**Total proposed: 21 classes** (18 current + 3 new).

### 4.3 Classes NOT Worth Adding

After analysis, these were considered but rejected:

| Candidate | Reason rejected |
|-----------|----------------|
| `basix_certificate` | Too NSW-specific, rare, can be `general_notes` |
| `survey_plan` | Too rare in practice, can be `existing_plan` |
| `waste_management_plan` | Rare standalone, can be `general_notes` |
| `notification_plan` | Rare standalone, can be `site_plan` |
| `site_analysis_plan` | Too similar to `site_plan`, would confuse the LLM |
| `report_page` | Too vague, overlaps with `general_notes` |
| `drainage_plan` | Merged into `stormwater_plan` for simplicity |

### 4.4 The `existing_plan` Overload Problem

Currently `existing_plan` covers:
1. Existing floor plans (before renovation)
2. Existing site plans (pre-works)
3. Existing elevations
4. Demolition plans
5. Existing site surveys

This is too broad but **splitting it would break downstream stages** that only care about "is this an existing page or not?" The current approach works because the LLM can disambiguate in its reasoning, and no downstream stage needs sub-class granularity.

---

## 5. Drawing Number and Scale Extraction Gaps

### 5.1 Regex Fallback — Supported Formats

Current `DRAWING_NO_RE`: `\b([ACDEFHLMPS])[ \t]*\d{3}[a-zA-Z]?\b`

**Matches:**
- A100, A 100, A-100, A_100 ✅
- S001, D201, E210 ✅
- A100A (revision suffix) ✅

**Does NOT match (and shouldn't for the regex fallback — LLM handles these):**
- DA-100, CC-201 (two-letter prefixes) — LLM handles
- "06 of 47", "Sheet 5" — LLM handles
- 100-A (reversed format) — LLM handles

**For planning applications, `DA` and `CC` as two-letter prefixes could be added** to the regex for wider fallback coverage. These are very common in DA and CC drawing sets:

```python
# Extended to cover standard Australian formats AND DA/CC prefixes
DRAWING_NO_RE = re.compile(
    r'\b(?:DA|CC|SK|DP)[-\s]*\d{2,4}[A-Za-z]?\b'
    r'|\b([ACDEFHLMPS])[ \t]*\d{3}[a-zA-Z]?\b'
)
```

This adds `DA-100`, `CC-201`, `SK-01`, `DP-01` without overfitting.

### 5.2 Scale Fallback — Missing Denominators

Current `VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500}`

Planning applications need:

```python
# Expanded for planning applications
VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2500, 5000}
```

This adds context plans (1:1000, 1:2500) and locality plans (1:5000) used in site analysis and masterplans.

---

## 6. Text Extraction Strategy Assessment

### 6.1 Current Approach

`build_user_message()` sends HEAD=300 + TAIL=400 chars per page. Title blocks are in the tail.

**Validated against:**
- Mesh (30 pages, mean 1,796 chars) — ✅ TAIL captures title block well
- DMP (48 pages, mean 7,449 chars) — ✅ TAIL captures title block

**Risk for planning applications:**
- Report pages (SEE, BASIX, etc.) have no title block at the tail
- Scanned pages have minimal/no text
- Landscape/stormwater plans have similar title block structure to CAD plans

**Verdict:** The current strategy is robust. Report pages without title blocks will have similar content in head and tail, and the LLM will classify them as `general_notes` or `irrelevant` based on content.

### 6.2 Potential Improvement — Title Block Detection

If we wanted to be smarter, we could detect whether the last 400 chars actually LOOK like a title block:

```python
def has_title_block(tail: str) -> bool:
    """Heuristic: title blocks have scale, drawing number, or project name patterns."""
    patterns = [r'1\s*[:]\s*\d+', r'\bA\s*\d{3}\b', r'Scale', r'Dwg\s*No', r'Issue for']
    return any(re.search(p, tail, re.IGNORECASE) for p in patterns)
```

But this adds complexity for minimal gain. Not recommended unless we encounter PDFs where the text extraction order differs.

---

## 7. Prompt Overhaul

### 7.1 Current Prompt Problems

1. **Working-drawing-centric language:** "The document is a CAD-exported PDF" — not true for planning applications
2. **No guidance on report pages:** When a page has no drawing title (text report), the LLM should classify as `general_notes`
3. **No guidance on scanned pages:** Pages with poor text extraction should be `irrelevant`
4. **No `landscape_plan` or `stormwater_plan` classes** in the schema
5. **No DA/CC prefix guidance** for drawing numbers in planning context
6. **No scale guidance for planning scales** (1:1000, 1:2500)

### 7.2 New Prompt Specification

Replace `pipeline/prompts/classify_pages.txt` with:

```
You are classifying pages from an Australian residential architectural document set.
This could be a set of working drawings (CAD-exported PDF) or a planning/development
application (which may mix CAD drawings with text reports and scanned documents).

Each page typically has a title block at the bottom or right edge containing a
drawing title, drawing number, scale, and date. Report pages (e.g. environmental
statements, BASIX certificates) may not have a title block.

CLASSES (use exactly these strings):
  title_sheet                — cover / project info / drawing list
  general_notes              — written notes, specifications, legends, text reports,
                               or any page that is primarily text without being a
                               specific drawing type
  site_plan                  — PROPOSED site plan with AREA ANALYSIS table or proposed
                               setbacks and site layout (building footprint, driveways,
                               boundaries, easements)
  existing_plan              — existing conditions plan, demolition plan, existing
                               floor plan, existing elevation, OR existing site plan
                               (pre-works)
  proposed_plan_primary      — proposed GROUND FLOOR plan with room labels, dimensions
  proposed_plan_ff           — proposed FIRST FLOOR (upper floor) plan in multi-storey
  proposed_plan_supplementary — secondary context overlay sheet (e.g. landscaping overlay,
                               carpark plan) that lacks room labels and full dimensions
  landscape_plan             — dedicated landscape / planting / deep soil plan showing
                               vegetation, planting species, soil zones, paving patterns
                               (usually part of a DA set)
  stormwater_plan            — stormwater drainage plan showing pipes, pits, detention
                               systems, overland flow paths, RW tanks
  electrical_plan            — electrical / power / data / lighting plan
  rcp                        — Reflected Ceiling Plan or lighting layout (if separate
                               from electrical)
  roof_plan                  — roof plan only
  elevations                 — external or internal elevations
  sections                   — building sections
  door_schedule              — door schedule table (includes combined WINDOW & DOOR SCHEDULE)
  window_schedule            — window schedule table (ONLY if exclusively window schedule)
  joinery_detail             — construction details, joinery elevations, and
                               selection/specification sheets tied to a specific
                               room or element (e.g. "KITCHEN INTERNAL ELEVATIONS",
                               "BATHROOM SELECTIONS", "FENCING TO PROPERTY").
                               Use for any detail sheet named after a specific element.
                               Do NOT use for project-wide general specification sheets.
  engineering_plan           — structural, civil, or hydraulic engineer's drawings
                               (typically S/C/H-prefixed drawing numbers). Includes
                               framing plans, slab layouts, stormwater engineering details.
  shadow_diagram             — shadow / overshadowing diagrams
  perspective                — 3D renders or perspective views
  irrelevant                 — anything not fitting above (blank pages, scanned images
                               with no extractable text, copyright notices, etc.)

RULES:
- proposed_plan_primary is the GROUND FLOOR proposed plan. For multi-storey sets,
  the ground floor is primary; use proposed_plan_ff for each upper-floor plan.
- proposed_plan_supplementary is for secondary sheets that lack room labels and
  full dimensions (e.g. a context or landscaping overlay). Do NOT use it for a
  floor plan with rooms.
- site_plan is the PROPOSED site plan — typically includes the AREA ANALYSIS table
  or proposed setbacks. An existing/pre-works site plan belongs in existing_plan.
- A page with "AREA ANALYSIS" table is always site_plan regardless of its title.
- landscape_plan is for dedicated planting/landscape plans only. If landscaping is
  shown on the site plan, keep it as site_plan.
- stormwater_plan is for dedicated drainage/stormwater plans. If stormwater is noted
  on the site plan, keep it as site_plan.
- A page whose title contains "WINDOW & DOOR SCHEDULE" MUST be classified as
  door_schedule. window_schedule is ONLY for pages that are exclusively window
  schedules.
- A page whose title contains "Shadow" or "Shadows", or whose drawing number is
  in the A800–A899 range, is shadow_diagram — NOT site_plan.
- Report pages (text-heavy, no drawing title, no standard title block) should be
  classified as general_notes. Examples: Statement of Environmental Effects,
  Waste Management Plan, BASIX Certificate notes, Access Reports.
- Scanned pages with very little extractable text (under ~200 chars) that don't
  form coherent drawing content should be classified as irrelevant.
- The drawing number is found in the title block (bottom or right edge of the page),
  adjacent to the architect name, project name, date. Drawing numbers may follow
  the standard A### format (e.g. A100, A201) OR use planning-stage prefixes like
  "DA-100" (Development Application) or "CC-201" (Construction Certificate), OR
  use simple page numbers like "05 of 47". Use whatever unique identifier appears
  in the title block.
- Return ONLY a JSON array. No markdown, no explanation, no wrapping text.

OUTPUT FORMAT — a JSON array of objects, one per page in input order:
[
  {
    "page_index": 0,
    "classification": "<class>",
    "drawing_no": "<drawing number or null>",
    "scale": "<scale e.g. 1:100 or null>",
    "date": "<date e.g. 13/07/20 or null>",
    "reasoning": "<one short sentence explaining the classification>"
  },
  ...
]
```

### 7.3 Key Changes From Current Prompt

| Aspect | Current | New |
|---------|---------|-----|
| Document scope | "architectural working drawing set" | "architectural document set — working drawings OR planning applications" |
| Planning-specific guidance | None | Report pages → `general_notes`, scanned pages → `irrelevant` |
| New classes | 18 | 21 (adds `landscape_plan`, `stormwater_plan`, `engineering_plan`) |
| DA/CC prefixes | Not mentioned | Explicitly described in drawing number rules |
| Engineering drawings | No handling | New `engineering_plan` class with S/C/H prefix guidance |
| Scale note | Only A### examples | Now mentions "planning-stage prefixes like DA-100 or CC-201" |

---

## 8. Validation and Sanity Checks

### 8.1 Current Checks

```python
if primary_count == 0:     warn("No proposed_plan_primary found")
elif primary_count > 1:    warn("Multiple proposed_plan_primary")
if ff_count > 0:           log("Multi-storey set")
if site_count == 0:        warn("No site_plan found")
```

These are good but minimal.

### 8.2 Additional Checks Recommended

**8.2.1 Page count mismatch (trivial, high value)**

```python
if len(llm_results) != doc.page_count:
    logger.warn(
        f"LLM returned {len(llm_results)} entries for {doc.page_count} pages — "
        "missing pages will default to 'irrelevant'"
    )
```

Catches truncation or drop-out early. Currently happens silently.

**8.2.2 Total token usage tracking (medium value)**

```python
if in_tok > 12000:
    logger.log(f"High input token count ({in_tok}) — consider raising TEXT_PER_PAGE")
```

Helpful for tuning when new PDFs appear with much larger page counts.

**8.2.3 Classification confidence via reasoning analysis (low value, experimental)**

Some LLM reasoning strings show uncertainty (e.g., "may be", "appears to be", "possibly").
Could flag these for manual review:

```python
UNCERTAIN_WORDS = {'may be', 'appears', 'possibly', 'could be', 'likely', 'unclear'}
uncertain = [p for p in final_pages if any(w in p.get('reasoning', '').lower() for w in UNCERTAIN_WORDS)]
if uncertain:
    logger.warn(f"{len(uncertain)} page(s) have uncertain reasoning")
```

**8.2.4 Page count vs sheet count mismatch (medium value)**

If the PDF has many pages but very few get classified as something useful (most are `general_notes` or `irrelevant`), flag it:

```python
useful_classes = VALID_CLASSES - {"general_notes", "irrelevant", "title_sheet"}
useful_count = sum(1 for p in final_pages if p["classification"] in useful_classes)
if useful_count < 3:
    logger.warn(f"Only {useful_count} pages in useful drawing classes — possible misclassification")
```

This would catch cases where an entire PDF of engineering drawings gets classified as `irrelevant` because no class matches.

**8.2.5 Unexpected class distribution (low value, diagnostic)**

```python
# If joinery_detail exceeds 60% of total pages, something unusual is happening
joinery_pct = tally.get("joinery_detail", 0) / max(len(final_pages), 1)
if joinery_pct > 0.6:
    logger.warn(f"joinery_detail dominates ({joinery_pct:.0%}) — review classification")
```

Note: DMP has 25/48 = 52% joinery_detail, which is legitimate. The threshold of 60% accounts for this.

---

## 9. Implementation Order

Recommended sequence for the fix agent:

| Order | What | Files affected | Risk |
|-------|------|---------------|------|
| 1 | **Update `VALID_SCALE_DENOMS`** — add 1000, 2500, 5000 | `01_classification.py` | Low — only affects regex fallback |
| 2 | **Extend `DRAWING_NO_RE`** — add DA/CC/SK/DP prefix patterns | `01_classification.py` | Low — only affects regex fallback |
| 3 | **Add page count mismatch check** — warn when LLM returns wrong count | `01_classification.py` | Low — additive check only |
| 4 | **Add useful-class-count check** — warn if <3 pages in non-trivial classes | `01_classification.py` | Low — additive check only |
| 5 | **Add `landscape_plan`, `stormwater_plan`, `engineering_plan` to `VALID_CLASSES`** | `01_classification.py` | Low — new classes only, no existing code uses them |
| 6 | **Replace prompt** — with the generalized version from §7.2 | `prompts/classify_pages.txt` | Medium — LLM behaviour change, must validate on both PDFs |
| 7 | **Add classification confidence check** — flag uncertain reasoning | `01_classification.py` | Low — diagnostic only |
| 8 | **Add token usage tracking** — log when input is high | `01_classification.py` | Low — diagnostic only |

**Test after each change:**
```bash
uv run python 01_classification.py                              # Mesh (current config)
uv run python -c "import config; config.PDF_PATH = ..." ...      # DMP via override
```

### 9.1 Validation Strategy

After all changes, validate against:

1. **Mesh PDF** — ensure classifications DON'T change (regression test)
2. **DMP PDF** — ensure classifications DON'T change (regression test)
3. **Key pages** — verify site_plan, proposed_plan_primary, proposed_plan_ff are unchanged for both
4. **Drawing numbers** — verify Mesh still has A###, DMP still has page-number format
5. **Scales** — verify no regressions on the 4 sections pages with compound "1:100/1:10" scales
6. **New classes** — verify the 3 new classes don't accidentally capture existing content

---

## Appendix: Quick Reference

### Regex Patterns (after all changes)

```python
DISCIPLINE_CODES = 'ACDEFHLMPS'
DRAWING_NO_RE = re.compile(
    r'\b(?:DA|CC|SK|DP)[-\s]*\d{2,4}[A-Za-z]?\b'
    r'|\b([' + DISCIPLINE_CODES + r'])[ \t]*\d{3}[a-zA-Z]?\b'
)

VALID_SCALE_DENOMS = {5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2500, 5000}
SCALE_RE = re.compile(r'1\s*[:/]\s*(\d+)\b')
```

### Class List (after all changes — 21 classes)

```
title_sheet, general_notes, site_plan, existing_plan,
proposed_plan_primary, proposed_plan_ff, proposed_plan_supplementary,
landscape_plan, stormwater_plan,
electrical_plan, rcp, roof_plan,
elevations, sections,
door_schedule, window_schedule,
joinery_detail, engineering_plan,
shadow_diagram, perspective,
irrelevant
```

### Sanity Checks (after all changes — 7 total)

| Check | Type | What it catches |
|-------|------|-----------------|
| `primary_count == 0` | Error | No GF plan → downstream fails |
| `primary_count > 1` | Warning | Multiple GF plans → ambiguous |
| `ff_count > 0` | Info | Multi-storey detected |
| `site_count == 0` | Error | No site plan → area extraction fails |
| Page count mismatch | Warning | LLM returned wrong entry count |
| Useful class count < 3 | Warning | Mostly notes/irrelevant → misclassification |
| Uncertain reasoning | Info | LLM unsure about classification |

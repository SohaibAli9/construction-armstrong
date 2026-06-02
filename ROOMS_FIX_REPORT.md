# Rooms Pipeline — Overhaul Research Report

**For the agent that will implement the fixes.** Everything needed to make all changes is documented here. Code changes are described — not implemented.

---

## Contents

1. [Research findings — Australian residential drawing conventions](#1-research-findings)
2. [Schema gap — fix `build_room_summary()` & Flash output format](#2-schema-gap-fix)
3. [Python validator on Flash output](#3-python-validator-on-flash-output)
4. [Fix `__main__` blocks — `.pages` extraction bug](#4-fix-__main__-blocks)
5. [Prompt overhaul — full spec](#5-prompt-overhaul)
6. [Split-span handling for Python](#6-split-span-handling-for-python)
7. [Dimension string handling — comma separators](#7-dimension-string-handling)
8. [Shed/outbuilding filtering](#8-shedoutbuilding-filtering)
9. [Implementation order](#9-implementation-order)

---

## 1. Research Findings

### 1.1 Font Size Conventions — Critical Variation

Two sample PDFs from different architects show COMPLETELY different font size conventions:

| Property | Mesh Reservoir (Mesh Design) | DMP Northcote (The Makeover Group) |
|---|---|---|
| Room label size | **9.9 pt** | **7.78 pt** |
| Annotation/legend size | 7.2 pt | 5.83 pt |
| Secondary annotation layer | — | 6 pt (564 spans — spec notes) |
| Gap between sizes | Clear (2.7 pt gap) | Narrow (~1.9 pt to 6pt layer) |
| Adaptive threshold result | 9.0 pt (perfect) | 6.5 pt (fallback, too low) |
| Total text spans | 336 | 717 |
| Font family | Likely sans-serif at 3.5mm AS1100 | Possibly 2.5mm minor-label size |
| Dimension format | "4851" (plain) | "4,851" (comma separator) |

**AS 1100.101 reference:** Standard specifies 3.5mm text height for room names on A1/A3 sheets. At 1:100 scale with 72dpi PDF export: `3.5mm → 350mm real → 9.92pt`. Mesh follows this exactly. DMP uses a smaller convention (~2.5mm → 7.1pt, measured 7.78pt due to font x-height differences).

**Implication for prompt: NEVER hardcode absolute point sizes.** Use relative language: "the second-largest font size cluster" or "the size group above dimension annotations."

### 1.2 Room Naming Variation

Same room, different architect conventions:

| Room type | Mesh label | DMP label |
|---|---|---|
| Dining | "Dining" | "MEALS" |
| Study | "Study" | "HOME OFFICE" |
| Pantry | "Pty" | "WIP" (Walk-In Pantry) |
| Laundry | "Ldy" | "LAUNDRY" |
| Walk-in Linen | — | "WIL" |
| Hall | "Hall" (separate from Entry) | "PASSAGE" |
| Living | "Living" | "LIVING" + "FAMILY" (sometimes) |
| Outdoor Living | "Outdoor" + "Living" (spans) | "ALFRESCO" or "DECK" |
| Bedroom | Bed 01, 02, 03 | BED 2 |
| Ensuite | ENS | (none on GF) |
| Powder Room | Pdr | WC (at annotation size) |

### 1.3 Common Room Types in Australian Homes

Based on research across real floor plans (build.com.au, SBS Australia, NSW ePlanning documents, Home Building Hub):

**Core rooms (nearly every plan):**
- Living / Family / Lounge
- Kitchen
- Dining / Meals
- Bedrooms (Bed 01/02/03 or Master/Bed 2/Bed 3)
- Bathroom (Bath)
- Laundry (Ldry, Ldy, LAUNDRY)
- WC / Powder Room (Pdr)

**Common additions:**
- WIR (Walk-In Robe — nearly standard in master)
- WIP (Walk-In Pantry — modern standard)
- WIL (Walk-In Linen — common)
- Study / Home Office (increasing post-COVID)
- Ensuite (ENS — standard with master bedroom)
- Entry / Foyer / Hall
- Porch
- Outdoor Living / Alfresco
- Sitting / Retreat
- Rumpus / Theatre / Media
- Garage

**Abbreviation standards (confirmed via build.com.au & Home Building Hub):**
- WIR = Walk In Robe
- WIP = Walk In Pantry
- WIL = Walk In Linen
- ENS = Ensuite
- PDR = Powder Room
- WC = Water Closet (toilet)
- BIR = Built-In Robe
- LDRY / LDY = Laundry

### 1.4 Combined Labels Pattern

Both PDFs show combined/slash labels in annotation zones — NEVER in the plan body:
- "KITCHEN / LIVING / DINING" (Mesh — 7.2pt annotation)
- "BED 01 / STORE" (Mesh — 7.2pt annotation)
- "ENS / BATH" (Mesh — 7.2pt annotation)
- "BED 2/BATH" (DMP — 5.83pt legend)
- "STAIRS/MEALS" (DMP — 5.83pt legend)

The presence of a slash is a strong indicator the span is annotation, not a canonical room label.

### 1.5 Current Regex Pattern Assessment

The existing `ROOM_LABELS` dict has 17 patterns. Assessment against observed data:

| Pattern | Status | Issue |
|---|---|---|
| `outdoor_living` | ❌ | Won't match split spans "Outdoor" + "Living" |
| `living` | ✅ | Works but catches "Living" from outdoor_living |
| `bedroom` | ✅ | `Bed\s*0?\d` matches Bed 01, BED 2 |
| `wir` | ✅ | WIR |
| `ensuite` | ✅ | ENS, Ensuite |
| `powder_room` | ✅ | Pdr, Powder, WC, Toilet |
| `bathroom` | ✅ | Bath, Bathroom |
| `laundry` | ✅ | Ldy, Laundry, WIL (WIL is debatable) |
| `kitchen` | ✅ | Kitchen |
| `dining` | ✅ | Dining, Meals |
| `sitting` | ✅ | Sitting |
| `entry` | ⚠️ | Catches "Hall" too — should be separate type |
| `porch` | ✅ | Porch |
| `study` | ✅ | Study, Home Office, Office |
| `pantry` | ✅ | Pty, Pantry, WIP |
| `shed` | ❌ | False positive — catches "Shed" outside dwelling |
| `garage` | ✅ | Unused in samples but correct |

### 1.6 The `.pages` Bug

`03_rooms.py` & `03b_rooms_flash.py` `__main__` blocks load classifications with:
```python
cl = json.loads(args.classifications.read_text())
main(PDF_PATH, cl, OUTPUT_DIR)
```

But `classification_report_flash.json` is `{"pages": [...], "cost_usd": ...}` — a dict, not a list. The `main()` function then iterates `classifications` looking for `"proposed_plan_primary"` which iterates dict keys ("pages", "cost_usd") → never finds a match and falls back to page index 5 (hardcoded default).

`run_all.py` (line 128-129) correctly handles this: `classifications = raw_cl["pages"]`. The `__main__` blocks in both room files do NOT.

---

## 2. Schema Gap Fix

### 2.1 Problem

`build_room_summary()` in `03_rooms.py` (lines 151-165) only returns 12 room types. It's missing:

| Missing type | Present in Mesh centroids | Present in DMP centroids |
|---|---|---|
| `entry` | ✅ (2x: Entry + Hall) | ✅ (ENTRY) |
| `porch` | ✅ (Porch) | ✅ (PORCH — DMP) |
| `outdoor_living` | ❌ (needs merge) | varies (Alfresco) |
| `hall` | ✅ (H centroid) | varies (PASSAGE) |
| `shed` | ✅ (false positive) | — |

The Flash prompt's output format has the same gap — only 12 keys.

### 2.2 Fix — `03_rooms.py`

Add to `build_room_summary()` return dict (after line 165):

```python
"entry":          {"count": len(found_rooms.get("entry", []))},
"porch":          {"count": len(found_rooms.get("porch", []))},
"outdoor_living": {"count": len(found_rooms.get("outdoor_living", []))},
"hall":           {"count": len(found_rooms.get("hall", []))},
```

But also **add `"hall"` to `ROOM_LABELS`** — currently `entry`'s regex `\b(?:Entry|Foyer|Hall)\b` catches Hall. Split it:

```python
"entry": re.compile(r'\b(?:Entry|Foyer)\b', re.IGNORECASE),
"hall":  re.compile(r'\bHall\b',             re.IGNORECASE),
```

Wait — but "Hall" at (461, 359) in Mesh IS a corridor/hallway label. Is it a "room" type we want? In the floor plan, the hallway is "Hall". It's a distinct space. Treating it as a separate type is correct architecturally. The GT from CLAUDE.md: expected rooms don't mention "hall" but the centroid IS valid. Adding it to the schema makes it available downstream — the GT can be updated later.

### 2.3 Fix — Flash output format (`extract_rooms.txt`)

Add `entry`, `porch`, `outdoor_living`, and `hall` to the FLASH output format in the `rooms` section:

```json
{
  "rooms": {
    "bedrooms":      { "count": <int>, "labels": [...] },
    "ensuite":       { "count": <int> },
    "bathroom":      { "count": <int> },
    "powder_room":   { "count": <int> },
    "kitchen":       { "count": <int> },
    "laundry":       { "count": <int> },
    "wir":           { "count": <int> },
    "pantry":        { "count": <int> },
    "study":         { "count": <int> },
    "living":        { "count": <int> },
    "dining":        { "count": <int> },
    "sitting":       { "count": <int> },
    "entry":         { "count": <int> },
    "porch":         { "count": <int> },
    "outdoor_living":{ "count": <int> },
    "hall":          { "count": <int> }
  },
  ...
}
```

---

## 3. Python Validator on Flash Output

### 3.1 What it should do

After `03b_rooms_flash.py` runs, before writing `rooms_flash.json`, run a validation step that checks **internal consistency** between centroids and room counts:

```
FOR each room type in canonical_centroids:
    count_in_centroids = number of centroids with that type
    count_in_rooms = rooms[type_name].count
    
    IF count_in_centroids != count_in_rooms:
        WARN: "Flash inconsistency: {type} has {count_in_centroids} centroids but rooms.count={count_in_rooms}"
        OVERRIDE: rooms[type_name].count = count_in_centroids
```

This would have caught all 4 DMP Northcote inconsistencies (dining, study, laundry, wir).

### 3.2 Implementation

Add to `03b_rooms_flash.py` `main()`, after Line 170 (where centroids are extracted) and before writing output:

```python
def validate_flash_counts(flash_rooms: dict, flash_centroids: list[dict]) -> dict:
    """Check centroids match room counts; fix mismatches. Returns corrected rooms dict."""
    # Map centroid type names to rooms dict keys
    type_to_key = {
        "bedroom": "bedrooms", "bedrooms": "bedrooms",
        "ensuite": "ensuite", "bathroom": "bathroom",
        "powder_room": "powder_room", "kitchen": "kitchen",
        "laundry": "laundry", "wir": "wir", "pantry": "pantry",
        "study": "study", "living": "living", "dining": "dining",
        "sitting": "sitting", "entry": "entry", "porch": "porch",
        "outdoor_living": "outdoor_living", "hall": "hall",
    }
    centroid_counts: dict[str, int] = {}
    for c in flash_centroids:
        ct = c.get("type", "")
        key = type_to_key.get(ct, ct)
        centroid_counts[key] = centroid_counts.get(key, 0) + 1
    
    fixed = {}
    for key, info in flash_rooms.items():
        expected = centroid_counts.get(key, 0)
        current = info.get("count", 0)
        if expected != current:
            logger.warn(f"Flash count mismatch: {key} has {current} in rooms but {expected} centroids — fixing")
            info["count"] = expected
        fixed[key] = info
    
    # Add any centroids without a rooms entry
    for key, count in centroid_counts.items():
        if key not in fixed:
            logger.warn(f"Flash missing rooms key '{key}' — adding from centroids ({count})")
            fixed[key] = {"count": count}
    
    return fixed
```

Call this before writing output: `flash_rooms = validate_flash_counts(flash_rooms, flash_centroids)`

### 3.3 Should we also validate against Python counts?

The existing `diff_vs_python()` function already compares counts. It should remain as a diagnostic (informational only) — do NOT use it to override Flash counts. Python is the baseline but Flash is the primary for the pipeline. The centroid-based consistency check is the authoritative validator.

---

## 4. Fix `__main__` Blocks

Both `03_rooms.py` (lines 245-246) and `03b_rooms_flash.py` (line 247) have:

```python
cl = json.loads(args.classifications.read_text())
main(PDF_PATH, cl, OUTPUT_DIR)
```

Fix (identical for both files):

```python
raw = json.loads(args.classifications.read_text())
if isinstance(raw, dict) and "pages" in raw:
    cl = raw["pages"]
else:
    cl = raw
main(PDF_PATH, cl, OUTPUT_DIR)
```

---

## 5. Prompt Overhaul

### 5.1 Current Prompt Problems

1. **Address-specific**: "58 Locksley Avenue, Reservoir VIC" — literal project address
2. **Expected room list**: Lists 17 specific room names for Mesh Reservoir
3. **Hardcoded sizes**: "~9.5–10.5pt → real labels, ~6.5–7.5pt → legend" — these are Mesh-specific
4. **Missing keys**: No `entry`, `porch`, `outdoor_living`, `hall` in output format
5. **No consistency rule**: Doesn't enforce centroids ↔ rooms count consistency
6. **Mesh-specific examples**: Combined label examples are from Mesh ("KITCHEN / LIVING / DINING", etc.)

### 5.2 New Prompt Specification

**Replace `pipeline/prompts/extract_rooms.txt`** with the following structure:

```
You are extracting room inventory from an Australian residential architectural 
floor plan (typically A201 — Proposed Ground Floor Plan).

INPUT:
A list of text spans extracted from the vector PDF. Each span has:
  - label: the text string
  - x_pt, y_pt: centroid position in PDF points (origin top-left)
  - size: rendered font size in points

TEXT LAYERS:
These drawings have multiple text layers at different font sizes:
  1. TITLE / drawing number     → largest (12pt+) — ignore
  2. ROOM LABELS                → second-largest cluster — these are canonical (keep)
  3. Dimension annotations      → smaller than room labels (ignore for rooms)
  4. Legend / title block       → smallest (ignore)
  5. Specification notes        → smallest (ignore)

HOW TO IDENTIFY CANONICAL ROOM LABELS:
- Room labels are the SECOND-LARGEST font size cluster on the page 
  (below the drawing title, above dimension numbers).
- They are positioned INSIDE the floor plan body (roughly the center 60-70% 
  of the page), not along page edges.
- They are single labels for individual room spaces (not combined with slashes).
- Each distinct room space has exactly ONE canonical label.

RULES:
- If the same label appears at both the room-label size and a smaller size, 
  the larger-size version is canonical.
- Combined labels containing slashes ("KITCHEN / LIVING / DINING", "BED 2/BATH", 
  "ENS / BATH", "STAIRS/MEALS") always appear in annotation/legend zones at 
  small font sizes — do NOT count them as rooms.
- Labels outside the plan body (in title block, revision notes, legend rows near 
  page edges) should be ignored.
- Count each distinct room space exactly once.
- For bedrooms, extract the specific labels (e.g. "Bed 01", "Bed 02", "BED 2").

ROOM TYPE MAPPING — map labels to these standardized types:
  bedroom:      Bed 01, Bed 02, Bed 03, BED 2, BED 3, Master Bedroom, Bedroom
  ensuite:      ENS, Ensuite
  bathroom:     Bath, Bathroom, BATH
  powder_room:  Pdr, Powder Room, WC, Toilet, PDR
  laundry:      Laundry, Ldry, Ldy, LAUNDRY, WIL (Walk-in Linen)
  kitchen:      Kitchen, KITCHEN
  dining:       Dining, Meals, MEALS
  living:       Living, Family, Lounge, LIVING
  sitting:      Sitting, Retreat
  entry:        Entry, Foyer
  hall:         Hall, Passage
  porch:        Porch, PORCH
  study:        Study, Home Office, Office, HOME OFFICE
  pantry:       Pantry, Pty, WIP (Walk-in Pantry), WIP
  wir:          WIR, Walk-in Robe
  outdoor_living: Outdoor Living, Alfresco, Deck (if labeled as living space)

IGNORE these common non-room labels:
  - Floor finishes: CARPET, TILES, TIMBER, CONCRETE, etc.
  - Tags: D01-D14, W01-W09, TC01, etc.
  - Level annotations: FFL, NGL, "Porch 79.95"
  - Construction notes: "NOGGINGS", "STUDS", "PROPOSED SHED", etc.
  - Door/window/fixture labels: SL, CBD, SHOWER, ROBE, etc.
  - Title block: drawing number, scale, architect name, project address
  - Separate outbuildings: sheds, garages (unless part of main dwelling)
  - Legend annotations like "EXISTING WALLS", "NEW WALLS", "DEMOLISHED"

OUTPUT FORMAT — Return ONLY a JSON object. No markdown, no explanation:

{
  "rooms": {
    "bedrooms":       { "count": <int>, "labels": ["Bed 01", "Bed 02", ...] },
    "ensuite":        { "count": <int> },
    "bathroom":       { "count": <int> },
    "powder_room":    { "count": <int> },
    "kitchen":        { "count": <int> },
    "laundry":        { "count": <int> },
    "wir":            { "count": <int> },
    "pantry":         { "count": <int> },
    "study":          { "count": <int> },
    "living":         { "count": <int> },
    "dining":         { "count": <int> },
    "sitting":        { "count": <int> },
    "entry":          { "count": <int> },
    "porch":          { "count": <int> },
    "outdoor_living": { "count": <int> },
    "hall":           { "count": <int> }
  },
  "canonical_centroids": [
    {
      "label": "<room label text>",
      "type": "<room_type>",
      "x_pt": <float>,
      "y_pt": <float>,
      "size": <float>,
      "reasoning": "<why this is canonical>"
    }
  ],
  "ignored_spans": [
    "<label> (reason for ignoring)"
  ],
  "overall_reasoning": "<one paragraph explaining size clusters and dedup decisions>"
}
```

CONSISTENCY REQUIREMENT:
  The "count" for each room type MUST exactly equal the number of centroids 
  of that type. Double-check before returning.

Return ONLY the JSON object. No markdown fences, no wrapper text.
```

### 5.3 Key changes from current prompt

| Aspect | Old | New |
|---|---|---|
| Address-specific content | Yes (58 Locksley Ave) | Removed |
| Explicit room list | Mesh-specific | General with mapping table |
| Font sizes | Hardcoded 9.5-10.5 / 6.5-7.5 | Relative ("second largest cluster") |
| Room type mappings | Implicit (in Python regex) | Explicit in prompt |
| Output format keys | 12 rooms | 16 rooms (adds entry, porch, outdoor_living, hall) |
| Ignored labels | 5 examples | 8 categories |
| Consistency rule | Missing | Added |
| Combined labels | Mesh-specific only | Both examples |
| Bedroom labels | Not described | Explicit extraction |
| Non-label items | Not described | Complete categories |

---

## 6. Split-Span Handling for Python

### 6.1 Problem

"Outdoor" (885.6, 353.4, 9.9pt) and "Living" (884.0, 364.7, 9.9pt) are two separate PyMuPDF spans. The regex `\bOutdoor\s*Living\b` will never match them. The second "Living" falls through to the `living` pattern → living count becomes 2 (GT: 1).

### 6.2 Fix

After `classify_spans()` returns, run a post-processing merge pass on `room_centroids`:

```python
def merge_split_spans(centroids: list[dict], max_dx: float = 30, max_dy: float = 20) -> list[dict]:
    """
    Merge adjacent spans that appear to be split parts of a compound label.
    E.g. "Outdoor" + "Living" → "Outdoor Living" (type: outdoor_living)
    
    Known compound patterns to check after merging:
      - "Outdoor" + "Living" → "Outdoor Living"
      - "Dining" + "Room" → "Dining Room" (unlikely in CAD)
    """
    # Build proximity index
    merged = []
    used = set()
    
    for i, a in enumerate(centroids):
        if i in used:
            continue
        # Look for adjacent span that could complete a compound
        for j, b in enumerate(centroids):
            if j <= i or j in used:
                continue
            if abs(a["x_pt"] - b["x_pt"]) < max_dx and abs(a["y_pt"] - b["y_pt"]) < max_dy:
                combined = a["label"] + " " + b["label"]
                # Check if combined matches any room pattern
                for room_type, pattern in ROOM_LABELS.items():
                    if pattern.search(combined):
                        used.add(i)
                        used.add(j)
                        merged.append({
                            "label": combined,
                            "type":  room_type,
                            "x_pt":  (a["x_pt"] + b["x_pt"]) / 2,
                            "y_pt":  (a["y_pt"] + b["y_pt"]) / 2,
                            "size":  max(a["size"], b["size"]),
                        })
                        break
    
    # Return original centroids minus merged ones, plus new merged entries
    result = [c for i, c in enumerate(centroids) if i not in used]
    result.extend(merged)
    return result
```

This should run in `classify_spans()` just before returning the result dict (before line 141).

**Important:** Only merge spans at the same font size (room-label size) and close together. Don't merge small annotation spans. The 30pt/20pt thresholds are appropriate for A3 at 1:100.

---

## 7. Dimension String Handling

### 7.1 Problem

DMP Northcote uses comma thousand separators: "4,851" not "4851". The regex `r'^\d{3,5}$'` skips these. This doesn't affect room extraction (dimension strings are secondary output) but the count is wrong.

### 7.2 Fix

Update `DIM_STRING_RE` in BOTH files to optionally handle commas:

```python
DIM_STRING_RE = re.compile(r'^[\d,]{3,7}$')   # standalone dimension — handles "4,851"
```

And when extracting values (`classify_spans` line 124-132 and `03b_rooms_flash.py` lines 195-200), strip commas before parsing:

```python
val = int(text.replace(",", ""))
```

---

## 8. Shed/Outbuilding Filtering

### 8.1 Problem

Python regex matches "Shed" as a room type, but "Shed" at (1032, 206) in Mesh Reservoir is a separate garden shed, not a dwelling room. It's also in the plan body but outside the main building footprint.

### 8.2 Short-term fix

Remove `shed` from `ROOM_LABELS` — sheds and garages are not "rooms" for area/room-count purposes. The pipeline is designed for dwelling room inventory. If garage/shed data is needed, it should be a separate stage, not mixed into room counts.

### 8.3 Better approach (future)

If shed/garage detection is wanted, flag them separately rather than excluding:
```python
"garage": re.compile(r'\bGarage\b', re.IGNORECASE),
```
Keep `shed` removed (it was likely an early experiment that survived into the final code).

---

## 9. Implementation Order

Recommended sequence for the fix agent:

| Order | What | Files affected |
|---|---|---|
| 1 | **Fix `build_room_summary()`** — add entry, porch, outdoor_living, hall | `03_rooms.py` |
| 2 | **Split Hall from Entry in regex** — separate `hall` pattern | `03_rooms.py` |
| 3 | **Remove `shed` from ROOM_LABELS** | `03_rooms.py` |
| 4 | **Add split-span merge** — `merge_split_spans()` | `03_rooms.py` |
| 5 | **Fix dimension string regex** — handle commas | `03_rooms.py` + `03b_rooms_flash.py` |
| 6 | **Fix both `__main__` blocks** — extract `.pages` | `03_rooms.py` + `03b_rooms_flash.py` |
| 7 | **Add Flash validator** — centroid-to-counts consistency check | `03b_rooms_flash.py` |
| 8 | **Replace prompt** — with the generalized version above | `prompts/extract_rooms.txt` |
| 9 | **Update Flash output format** — add 4 missing room keys to schema | `prompts/extract_rooms.txt` |

**Test after each step:**
```bash
uv run python 03_rooms.py                              # Mesh default
uv run python 03b_rooms_flash.py                       # Mesh default
# Override PDF_PATH in config temporarily for DMP
```

---

## Appendix: Data Sources

- AS 1100.101-1992 Technical drawing — Part 101: General principles (via UTAS CAD standards PDF, Transport for NSW standards)
- build.com.au — "Breaking down floor plan abbreviations and symbols for home builders"
- SBS Australia — "Reading Australian floorplans: common terms explained"
- Home Building Hub — "Common terms found in drawings plans" (PDF)
- Real-world floor plans: Mesh Reservoir 620k mid (Mesh Design Projects), DMP Elm Northcote 750k (The Makeover Group)

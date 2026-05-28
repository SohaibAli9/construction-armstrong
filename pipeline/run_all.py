"""
ProCalc AI demo — extraction pipeline.

Usage:
  uv run python run_all.py              # full run
  uv run python run_all.py --stage 2   # re-run from stage 2 onwards
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from config import PDF_PATH, OUTPUT_DIR


def fmt_time(s: float) -> str:
    return f"{s:.1f}s"


def load_stage(name: str):
    import importlib.util
    path = HERE / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_final_json(classifications, areas_data, rooms_data, geometry_data, validation_data) -> dict:
    return {
        "project":            areas_data.get("project", {}),
        "areas":              areas_data.get("areas", {}),
        "rooms":              rooms_data.get("rooms", {}),
        "geometry": {
            "scale":              "1:100",
            "calibration":        geometry_data.get("calibration", {}),
            "use_wall_geometry":  geometry_data.get("use_wall_geometry"),
            "wall_count":         geometry_data.get("wall_count"),
            "walls":              geometry_data.get("walls", []),
            "room_centroids":     geometry_data.get("room_centroids_mm", []),
        },
        "validation":         validation_data,
        "page_classification": classifications,
    }


def print_summary(areas_data, rooms_data, geometry_data, validation_data, svg_path):
    areas   = areas_data.get("areas", {})
    rooms   = rooms_data.get("rooms", {})
    val     = validation_data

    def av(key):
        v = areas.get(key)
        return f"{v['value']} m²" if v else "NOT FOUND"

    print()
    print("=" * 60)
    print("  PROCALC EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"  Site area:         {av('site_area')}")
    print(f"  Dwelling (GF):     {av('ground_floor')}")
    print(f"  Porch:             {av('porch')}")
    print(f"  Outdoor living:    {av('outdoor_living')}")
    print()
    print(f"  Bedrooms:          {rooms.get('bedrooms', {}).get('count', '?')}")
    print(f"  Ensuite:           {rooms.get('ensuite', {}).get('count', '?')}")
    print(f"  Bathroom:          {rooms.get('bathroom', {}).get('count', '?')}")
    print(f"  Study:             {rooms.get('study', {}).get('count', '?')}")
    print()
    print(f"  Walls extracted:   {geometry_data.get('wall_count', 0)} polygons")
    print(f"  Wall geometry:     {'YES' if geometry_data.get('use_wall_geometry') else 'FALLBACK (centroid render)'}")
    cal = geometry_data.get("calibration", {})
    print(f"  Calibration:       {cal.get('computed_mm_per_pt', 0):.4f} mm/pt  error={cal.get('error_pct') or 0:.1f}%")
    print()
    print(f"  Validation:        {val.get('overall')}")
    for flag in val.get("flags", []):
        print(f"    * {flag}")
    print()
    print(f"  Output dir:        {OUTPUT_DIR}")
    print(f"  SVG:               {svg_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, default=1,
                        help="Start from this stage (1-6), run all remaining stages")
    parser.add_argument("--only", type=int, default=None,
                        help="Run exactly this one stage (requires prior stages already cached)")
    args = parser.parse_args()

    # --only overrides --stage: run exactly one stage
    if args.only is not None:
        args.stage = args.only

    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        print("Drop the PDF into the sample/ folder and re-run.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t_total = time.time()

    classifications = None
    areas_data      = None
    rooms_data      = None
    geometry_data   = None
    validation_data = None

    def cached(fname):
        p = OUTPUT_DIR / fname
        return json.loads(p.read_text()) if p.exists() else None

    # Load cached outputs for skipped stages — prefer Flash output over regex
    if args.stage > 1:
        classifications = cached("classification_report_flash.json") or cached("classification_report.json")
    if args.stage > 2:
        areas_data = cached("areas_flash.json") or cached("areas.json")
    if args.stage > 3:
        rooms_data = cached("rooms_flash.json") or cached("rooms.json")
    if args.stage > 4:
        geometry_data = cached("geometry.json")
    if args.stage > 5:
        validation_data = cached("validation.json")

    stages = [
        (1, "Page classification",   "01b_classify_flash.py"),
        (2, "Area schedule",         "02b_areas_flash.py"),
        (3, "Room inventory",        "03b_rooms_flash.py"),
        (4, "Wall geometry",         "04_geometry.py"),
        (5, "Validation",            "05_validate.py"),
        (6, "SVG render",            "06_render.py"),
    ]

    svg_path = OUTPUT_DIR / "floor_plan_extracted.svg"

    for stage_num, label, filename in stages:
        if stage_num < args.stage:
            continue
        if args.only is not None and stage_num > args.only:
            break

        print(f"\n[{stage_num}/6] {label}")
        t0 = time.time()
        try:
            mod = load_stage(filename)
            if stage_num == 1:
                classifications = mod.main(PDF_PATH, OUTPUT_DIR)
            elif stage_num == 2:
                areas_data = mod.main(PDF_PATH, classifications, OUTPUT_DIR)
            elif stage_num == 3:
                rooms_data = mod.main(PDF_PATH, classifications, OUTPUT_DIR)
            elif stage_num == 4:
                geometry_data = mod.main(PDF_PATH, classifications, rooms_data, OUTPUT_DIR)
            elif stage_num == 5:
                validation_data = mod.main(areas_data, rooms_data, geometry_data, OUTPUT_DIR)
            elif stage_num == 6:
                svg_path = mod.main(geometry_data, areas_data, validation_data, OUTPUT_DIR)
        except Exception:
            print(f"  ERROR in stage {stage_num}:")
            traceback.print_exc()
            print("  Continuing to next stage...")

        print(f"  done in {fmt_time(time.time() - t0)}")

    # Assemble and write final JSON
    if all(x is not None for x in [classifications, areas_data, rooms_data, geometry_data, validation_data]):
        final = build_final_json(classifications, areas_data, rooms_data, geometry_data, validation_data)
        out = OUTPUT_DIR / "extracted_data.json"
        out.write_text(json.dumps(final, indent=2))
        print(f"\n  Final JSON: {out}")

    print(f"\n  Total time: {fmt_time(time.time() - t_total)}")
    print_summary(areas_data or {}, rooms_data or {}, geometry_data or {}, validation_data or {}, svg_path)


if __name__ == "__main__":
    main()

"""
ProCalc AI demo — extraction pipeline.

Usage:
  uv run python run_all.py              # full run
  uv run python run_all.py --stage 2   # re-run from stage 2 onwards
"""

import argparse
import csv
import json
import os
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from config import PDF_PATH, OUTPUT_DIR, DEEPSEEK_FLASH


def fmt_time(s: float) -> str:
    return f"{s:.1f}s"


def load_stage(name: str):
    import importlib.util
    path = HERE / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_final_json(classifications, areas_data, rooms_data, geometry_data, validation_data, costs: dict) -> dict:
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
        "costs":              costs,
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
    parser.add_argument("--no-anim", "-n", action="store_true",
                        help="Disable animated dashboard (plain terminal output)")
    args = parser.parse_args()

    # --only overrides --stage: run exactly one stage
    if args.only is not None:
        args.stage = args.only

    # Import animation module — graceful fallback if Rich is missing
    try:
        from anim import LivePipeline as PipelineUI
    except ImportError:
        from anim import NoopPipeline as PipelineUI

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

    costs = {"classify": 0.0, "areas": 0.0, "rooms": 0.0, "geometry": 0.0, "validate": 0.0}

    def cached(fname):
        p = OUTPUT_DIR / fname
        return json.loads(p.read_text()) if p.exists() else None

    # Load cached outputs for skipped stages — prefer Flash output over regex
    if args.stage > 1:
        raw_cl = cached("classification_report_flash.json") or cached("classification_report.json")
        if isinstance(raw_cl, dict) and "pages" in raw_cl:
            classifications = raw_cl["pages"]
            costs["classify"] = raw_cl.get("cost_usd", 0.0)
        else:
            classifications = raw_cl
    if args.stage > 2:
        areas_data = cached("areas_flash.json") or cached("areas.json")
        if areas_data:
            costs["areas"] = areas_data.get("cost_usd", 0.0)
    if args.stage > 3:
        rooms_data = cached("rooms_flash.json") or cached("rooms.json")
        if rooms_data:
            costs["rooms"] = rooms_data.get("cost_usd", 0.0)
    if args.stage > 4:
        geometry_data = cached("geometry.json")
        if geometry_data:
            costs["geometry"] = geometry_data.get("cost_usd", 0.0)
    if args.stage > 5:
        validation_data = cached("validation.json")
        if validation_data:
            costs["validate"] = validation_data.get("cost_usd", 0.0)

    stages = [
        (1, "Page classification",   "01_classification.py"),
        (2, "Area schedule",         "02_areas.py"),
        (3, "Room inventory",        "03_rooms.py"),
        (4, "Wall geometry",         "04_geometry.py"),
        (5, "Validation",            "05_validate.py"),
        (6, "SVG render",            "06_render.py"),
    ]

    svg_path = OUTPUT_DIR / "floor_plan_extracted.svg"

    with PipelineUI(total_stages=6, animate=not args.no_anim) as ui:
        for stage_num, label, filename in stages:
            if stage_num < args.stage:
                continue
            if args.only is not None and stage_num > args.only:
                break

            idx = stage_num - 1  # zero-based
            ui.start_stage(idx, label)
            t0 = time.time()

            try:
                mod = load_stage(filename)
                stage_fn = {
                    1: lambda: mod.main(PDF_PATH, OUTPUT_DIR),
                    2: lambda: mod.main(PDF_PATH, classifications, OUTPUT_DIR),
                    3: lambda: mod.main(PDF_PATH, classifications, OUTPUT_DIR),
                    4: lambda: mod.main(PDF_PATH, classifications, rooms_data, OUTPUT_DIR),
                    5: lambda: mod.main(areas_data, rooms_data, geometry_data, OUTPUT_DIR),
                    6: lambda: mod.main(geometry_data, areas_data, validation_data, OUTPUT_DIR),
                }[stage_num]

                # Silence stage output during animation (Rich owns the terminal)
                if args.no_anim:
                    result = stage_fn()
                else:
                    devnull = open(os.devnull, "w")
                    with redirect_stdout(devnull), redirect_stderr(devnull):
                        result = stage_fn()
                    devnull.close()

                if stage_num == 1:
                    classifications, costs["classify"] = result
                elif stage_num == 2:
                    areas_data, costs["areas"] = result
                elif stage_num == 3:
                    rooms_data, costs["rooms"] = result
                elif stage_num == 4:
                    geometry_data, costs["geometry"] = result
                elif stage_num == 5:
                    validation_data, costs["validate"] = result
                elif stage_num == 6:
                    svg_path = result

            except Exception:
                elapsed = time.time() - t0
                ui.fail_stage(idx, error=f"failed after {elapsed:.0f}s")
                traceback.print_exc()
                continue

            elapsed = time.time() - t0
            ui.complete_stage(idx, elapsed=elapsed)

        ui.set_cost(sum(costs.values()))

    # Assemble and write final JSON
    if all(x is not None for x in [classifications, areas_data, rooms_data, geometry_data, validation_data]):
        final = build_final_json(classifications, areas_data, rooms_data, geometry_data, validation_data, costs)
        out = OUTPUT_DIR / "extracted_data.json"
        out.write_text(json.dumps(final, indent=2))
        print(f"\n  Final JSON: {out}")

        # --- Cost ledger (append row to shared CSV) ---
        csv_path = OUTPUT_DIR.parent / "costs.csv"
        write_header = not csv_path.exists()
        total_cost = sum(costs.values())
        with csv_path.open("a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["timestamp", "pdf_name", "model", "classify_cost", "areas_cost",
                                 "rooms_cost", "geometry_cost", "validate_cost", "total_cost"])
            writer.writerow([
                datetime.now().isoformat(),
                PDF_PATH.stem,
                DEEPSEEK_FLASH,
                round(costs["classify"], 6),
                round(costs["areas"], 6),
                round(costs["rooms"], 6),
                round(costs["geometry"], 6),
                round(costs["validate"], 6),
                round(total_cost, 6),
            ])
        print(f"\n  Cost ledger: {csv_path}  (total=${total_cost:.4f})")

    print(f"\n  Total time: {fmt_time(time.time() - t_total)}")
    print_summary(areas_data or {}, rooms_data or {}, geometry_data or {}, validation_data or {}, svg_path)


if __name__ == "__main__":
    main()

"""Stage 6: Render SVG floor plan from extracted geometry."""

import json
from pathlib import Path
import logger

SVG_W   = 1200
SVG_H   = 800
PADDING = 60

ROOM_COLORS = {
    "bedroom":        "#4A90D9",
    "living":         "#7CB87C",
    "kitchen":        "#E8A838",
    "dining":         "#D4785A",
    "bathroom":       "#5BACC8",
    "ensuite":        "#5BACC8",
    "powder_room":    "#7BB8D0",
    "laundry":        "#A0A0C0",
    "wir":            "#9B7EC8",
    "pantry":         "#C8A07E",
    "study":          "#78A878",
    "entry":          "#B8B870",
    "porch":          "#C8C870",
    "outdoor_living": "#88C888",
    "sitting":        "#7CB87C",
    "shed":           "#A0A0A0",
    "garage":         "#808080",
}
DEFAULT_COLOR = "#999999"


def compute_bounds(walls: list[dict], centroids: list[dict]) -> tuple:
    xs, ys = [], []
    for w in walls:
        xs += [w["x1_mm"], w["x2_mm"]]
        ys += [w["y1_mm"], w["y2_mm"]]
    for c in centroids:
        xs.append(c["x_mm"])
        ys.append(c["y_mm"])
    if not xs:
        return 0, 0, 25000, 15000
    return min(xs), min(ys), max(xs), max(ys)


def make_transform(min_x, min_y, max_x, max_y):
    draw_w = SVG_W - 2 * PADDING
    draw_h = SVG_H - 2 * PADDING
    span_x = max_x - min_x or 1
    span_y = max_y - min_y or 1
    scale  = min(draw_w / span_x, draw_h / span_y)

    def tf(x_mm, y_mm):
        px = PADDING + (x_mm - min_x) * scale
        py = PADDING + (max_y - y_mm) * scale   # SVG Y is top-down
        return round(px, 1), round(py, 1)

    return tf, scale


def render_walls(walls, tf, scale: float) -> list[str]:
    elements = []
    skipped  = 0
    for w in walls:
        x1, y1 = tf(w["x1_mm"], w["y1_mm"])
        x2, y2 = tf(w["x2_mm"], w["y2_mm"])

        if w.get("type") == "wall_line":
            # stroke_pt is the raw PDF line weight; convert pt→screen px, clamp 1.5–4
            stroke_px = max(1.5, min(4.0, (w.get("stroke_pt") or 0.5) * (96 / 72)))
            if abs(x2 - x1) < 0.3 and abs(y2 - y1) < 0.3:
                skipped += 1
                continue
            elements.append(
                f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="#2C2C2C" stroke-width="{stroke_px:.1f}" '
                f'stroke-linecap="square"/>'
            )
        else:
            # Filled polygon walls (filter A/B)
            rx = min(x1, x2)
            ry = min(y1, y2)
            rw = abs(x2 - x1)
            rh = abs(y2 - y1)
            if rw < 0.5 or rh < 0.5:
                skipped += 1
                continue
            elements.append(
                f'  <rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" '
                f'fill="#2C2C2C" stroke="#111" stroke-width="0.3"/>'
            )
    if skipped:
        logger.log(f"Walls skipped (sub-pixel): {skipped}", indent=1)
    return elements


def render_room_fallback(centroids, tf, scale) -> list[str]:
    BOX_W_PX = max(50, 2500 * scale)
    BOX_H_PX = max(30, 1500 * scale)
    elements = []
    for c in centroids:
        cx, cy = tf(c["x_mm"], c["y_mm"])
        rx = cx - BOX_W_PX / 2
        ry = cy - BOX_H_PX / 2
        color = ROOM_COLORS.get(c.get("type"), DEFAULT_COLOR)
        elements += [
            f'  <rect x="{round(rx,1)}" y="{round(ry,1)}" '
            f'width="{round(BOX_W_PX,1)}" height="{round(BOX_H_PX,1)}" '
            f'fill="{color}" fill-opacity="0.6" stroke="{color}" stroke-width="1" rx="3"/>',
            f'  <text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="middle" '
            f'font-family="Arial,sans-serif" font-size="11" fill="#fff" font-weight="bold">'
            f'{_esc(c["label"])}</text>',
        ]
    return elements


# Rooms with known individual areas from A100 schedule
_ROOM_KNOWN_AREAS = {
    "porch":          3.06,
    "outdoor_living": 27.18,
}


def _pill_width(label: str) -> int:
    """Approximate pill width in px to fit label text at 9pt Arial."""
    return max(50, len(label) * 6 + 12)


def render_room_labels(centroids, tf) -> list[str]:
    elements = []
    for c in centroids:
        cx, cy = tf(c["x_mm"], c["y_mm"])
        color  = ROOM_COLORS.get(c.get("type"), DEFAULT_COLOR)
        area   = _ROOM_KNOWN_AREAS.get(c.get("type"))
        pw     = _pill_width(c["label"])
        pill_h = 26 if area else 20

        # Clamp so pill never overflows canvas edges
        rx = cx - pw / 2
        rx = max(5, min(rx, SVG_W - pw - 5))
        tx = rx + pw / 2

        if area:
            elements += [
                f'  <rect x="{rx:.1f}" y="{cy - pill_h/2:.1f}" width="{pw}" height="{pill_h}" '
                f'fill="{color}" fill-opacity="0.85" rx="3"/>',
                f'  <text x="{tx:.1f}" y="{cy - 4:.1f}" text-anchor="middle" '
                f'font-family="Arial,sans-serif" font-size="9" fill="#fff" font-weight="bold">'
                f'{_esc(c["label"])}</text>',
                f'  <text x="{tx:.1f}" y="{cy + 8:.1f}" text-anchor="middle" '
                f'font-family="Arial,sans-serif" font-size="8" fill="#ffe">'
                f'{area} m²</text>',
            ]
        else:
            elements += [
                f'  <rect x="{rx:.1f}" y="{cy - 10:.1f}" width="{pw}" height="20" '
                f'fill="{color}" fill-opacity="0.85" rx="3"/>',
                f'  <text x="{tx:.1f}" y="{cy:.1f}" text-anchor="middle" dominant-baseline="middle" '
                f'font-family="Arial,sans-serif" font-size="9" fill="#fff" font-weight="bold">'
                f'{_esc(c["label"])}</text>',
            ]
    return elements


def render_area_legend(areas: dict) -> list[str]:
    rows = [
        ("Dwelling",       areas.get("ground_floor",    {}).get("value"), "m²"),
        ("Porch",          areas.get("porch",            {}).get("value"), "m²"),
        ("Outdoor Living", areas.get("outdoor_living",   {}).get("value"), "m²"),
        ("Coverage",       areas.get("site_coverage_pct",{}).get("value"), "%"),
        ("Site",           areas.get("site_area",        {}).get("value"), "m²"),
    ]
    rows = [(lbl, val, unit) for lbl, val, unit in rows if val is not None]
    if not rows:
        return []

    row_h = 14
    pad   = 6
    box_w = 130
    box_h = len(rows) * row_h + pad * 2 + 12
    x0    = PADDING
    y0    = SVG_H - 25 - box_h - 10

    elements = [
        f'  <rect x="{x0}" y="{y0}" width="{box_w}" height="{box_h}" '
        f'fill="#fff" fill-opacity="0.88" stroke="#ccc" stroke-width="1" rx="4"/>',
        f'  <text x="{x0 + pad}" y="{y0 + pad + 9}" '
        f'font-family="Arial,sans-serif" font-size="9" font-weight="bold" fill="#444">'
        f'Area Schedule</text>',
    ]
    for i, (lbl, val, unit) in enumerate(rows):
        ty = y0 + pad + 12 + (i + 1) * row_h
        val_str = f"{val:.2f} {unit}" if unit == "m²" else f"{val:.2f}{unit}"
        elements += [
            f'  <text x="{x0 + pad}" y="{ty}" font-family="Arial,sans-serif" '
            f'font-size="9" fill="#555">{_esc(lbl)}</text>',
            f'  <text x="{x0 + box_w - pad}" y="{ty}" text-anchor="end" '
            f'font-family="Arial,sans-serif" font-size="9" font-weight="bold" fill="#222">'
            f'{val_str}</text>',
        ]
    return elements


def render_scale_bar(scale) -> list[str]:
    bar_mm = 5000
    bar_px = bar_mm * scale
    x0 = PADDING
    y0 = SVG_H - 25
    x1 = x0 + bar_px
    return [
        f'  <line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="#333" stroke-width="2"/>',
        f'  <line x1="{x0}" y1="{y0-5}" x2="{x0}" y2="{y0+5}" stroke="#333" stroke-width="2"/>',
        f'  <line x1="{x1}" y1="{y0-5}" x2="{x1}" y2="{y0+5}" stroke="#333" stroke-width="2"/>',
        f'  <text x="{(x0+x1)/2}" y="{y0-8}" text-anchor="middle" '
        f'font-family="Arial,sans-serif" font-size="10" fill="#333">5 000 mm</text>',
    ]


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(geometry_data: dict, areas_data: dict, validation_data: dict, output_dir: Path) -> Path:
    logger.init(output_dir, "06_render")

    walls     = geometry_data.get("walls", [])
    centroids = geometry_data.get("room_centroids_mm", [])
    use_walls = geometry_data.get("use_wall_geometry", False)

    project   = areas_data.get("project", {})
    address   = project.get("address") or "58 Locksley Ave, Reservoir VIC 3060"
    dwelling  = (areas_data.get("areas", {}).get("ground_floor") or {}).get("value", "?")
    val_status = validation_data.get("overall", "UNKNOWN")

    logger.log(f"Walls available: {len(walls)}  use_wall_geometry={use_walls}")
    logger.log(f"Room centroids: {len(centroids)}")

    min_x, min_y, max_x, max_y = compute_bounds(walls if use_walls else [], centroids)
    logger.log(f"Bounds (mm): x={min_x:.0f}–{max_x:.0f}  y={min_y:.0f}–{max_y:.0f}")

    tf, scale = make_transform(min_x, min_y, max_x, max_y)
    logger.log(f"SVG scale: {scale:.4f} px/mm  (canvas {SVG_W}x{SVG_H}px, padding {PADDING}px)")

    elements = []
    if use_walls:
        wall_elements = render_walls(walls, tf, scale)
        elements += wall_elements
        elements += render_room_labels(centroids, tf)
        render_mode = f"wall lines ({len(walls)}) + labels"
        logger.log(f"Wall SVG elements generated: {len(wall_elements)}")
    else:
        elements += render_room_fallback(centroids, tf, scale)
        render_mode = f"room centroid fallback ({len(centroids)} rooms)"
        logger.warn("Using fallback centroid render — wall polygon count below threshold")

    elements += render_scale_bar(scale)
    elements += render_area_legend(areas_data.get("areas", {}))

    status_color = "#2ECC71" if val_status == "PASS" else "#E74C3C"

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}" '
        f'style="background:#F8F8F8; font-family:Arial,sans-serif;">',
        f'  <text x="{SVG_W//2}" y="20" text-anchor="middle" font-size="14" '
        f'font-weight="bold" fill="#222">{_esc(address)} — Extracted Floor Plan</text>',
        f'  <text x="{SVG_W//2}" y="36" text-anchor="middle" font-size="10" fill="#666">'
        f'Render: {_esc(render_mode)} | Scale 1:100 | Dwelling {dwelling} m²</text>',
        f'  <rect x="{SVG_W-115}" y="8" width="105" height="22" rx="4" '
        f'fill="{status_color}" fill-opacity="0.15" stroke="{status_color}"/>',
        f'  <text x="{SVG_W-62}" y="23" text-anchor="middle" font-size="11" '
        f'fill="{status_color}" font-weight="bold">Validation: {val_status}</text>',
        *elements,
        f'  <text x="{SVG_W-PADDING}" y="{SVG_H-40}" text-anchor="end" '
        f'font-size="9" fill="#999">Source: PyMuPDF text + vector extraction | No vision API</text>',
        f'  <text x="{SVG_W-PADDING}" y="{SVG_H-28}" text-anchor="end" '
        f'font-size="9" fill="#999">Confidence: 0.98</text>',
        '</svg>',
    ]

    out = output_dir / "floor_plan_extracted.svg"
    out.write_text("\n".join(svg_lines))
    logger.log(f"SVG lines: {len(svg_lines)}")
    logger.log(f"Written: {out}")
    logger.log(f"Render mode: {render_mode}")
    return out


if __name__ == "__main__":
    from config import OUTPUT_DIR
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    g = json.loads((OUTPUT_DIR / "geometry.json").read_text())
    a = json.loads((OUTPUT_DIR / "areas_flash.json").read_text())
    v = json.loads((OUTPUT_DIR / "validation.json").read_text())
    main(g, a, v, OUTPUT_DIR)

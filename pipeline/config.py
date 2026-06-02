import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_FLASH    = "deepseek-chat"   # maps to DeepSeek-V4 Flash

# DeepSeek V4 Flash pricing (per M tokens): $0.14 input, $0.28 output
DEEPSEEK_FLASH_INPUT_COST  = 0.14 / 1_000_000
DEEPSEEK_FLASH_OUTPUT_COST = 0.28 / 1_000_000

# Claude fallback (used when DEEPSEEK_API_KEY has no balance)
CLAUDE_MODEL       = "claude-sonnet-4-6"
# claude-sonnet-4-6 pricing (per M tokens): $3.00 input, $15.00 output
CLAUDE_INPUT_COST  = 3.00 / 1_000_000
CLAUDE_OUTPUT_COST = 15.00 / 1_000_000

ROOT       = Path(__file__).parent
SAMPLE_DIR = ROOT.parent / "sample"

PDF_PATH   = SAMPLE_DIR / "Mesh Reservoir 620k mid.pdf"
OUTPUT_DIR = ROOT.parent / "output" / PDF_PATH.stem

# Known page indices (0-based) — confirmed from document
PAGE_SITE_PLAN      = 2   # A100
PAGE_PROPOSED_PLAN  = 5   # A201
PAGE_SUPP_PLAN      = 4   # A200
PAGE_RCP            = 7   # A220

# Scale: 1:100, A3 paper, 1pt = 25.4/72 mm on paper
MM_PER_PT = (25.4 / 72) * 100   # = 35.2778 mm real-world per PDF point

# ── Ground truth per PDF ──────────────────────────────────────────────
# The lookup key is PDF_PATH.stem so ground truth auto-follows the PDF.
# Each entry that is None causes the corresponding validation check to SKIP.

_GROUND_TRUTHS: dict[str, dict] = {
    "Mesh Reservoir 620k mid": {
        "site_area":         527.14,
        "dwelling":          198.07,
        "porch":             3.06,
        "outdoor_living":    27.18,
        "coverage_pct":      41.72,
        "coverage_m2":       219.91,
        "overall_mm":        20490,
        "lighting_dwelling": 188.48,
        "lighting_porch":    1.98,
        "lighting_outdoor":  26.57,
        "expected_rooms": {
            "bedroom": 3, "wir": 1, "ensuite": 1, "bathroom": 1,
            "powder_room": 1, "laundry": 1, "kitchen": 1, "dining": 1,
            "living": 1, "sitting": 1, "entry": 1, "porch": 1,
            "study": 1, "pantry": 1, "outdoor_living": 1,
        },
    },
    "DMP Elm Northcote 750k": {
        "site_area":         233.03,
        "dwelling":          129.26,
        "porch":             6.79,
        "outdoor_living":    None,
        "coverage_pct":      58.38,
        "coverage_m2":       136.05,
        "overall_mm":        None,
        "lighting_dwelling": None,
        "lighting_porch":    None,
        "lighting_outdoor":  None,
        "expected_rooms":    {},
    },
}

_gt = _GROUND_TRUTHS.get(PDF_PATH.stem, {})

GT_SITE_AREA        = _gt.get("site_area")
GT_DWELLING         = _gt.get("dwelling")
GT_PORCH            = _gt.get("porch")
GT_OUTDOOR          = _gt.get("outdoor_living")
GT_COVERAGE_PCT     = _gt.get("coverage_pct")
GT_COVERAGE_M2      = _gt.get("coverage_m2")
GT_OVERALL_MM       = _gt.get("overall_mm")
GT_LIGHTING_DWELLING = _gt.get("lighting_dwelling")
GT_LIGHTING_PORCH   = _gt.get("lighting_porch")
GT_LIGHTING_OUTDOOR = _gt.get("lighting_outdoor")
GT_EXPECTED_ROOMS   = _gt.get("expected_rooms", {})

CALIBRATION_ERROR_THRESHOLD = 0.05   # 5%
AREA_DELTA_FLAG_M2           = 20.0   # flag if dwelling delta > this

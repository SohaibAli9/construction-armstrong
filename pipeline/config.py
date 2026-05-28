import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_FLASH    = "deepseek-chat"   # DeepSeek-V3 (Flash tier)

DEEPSEEK_FLASH_INPUT_COST  = 0.14 / 1_000_000
DEEPSEEK_FLASH_OUTPUT_COST = 0.28 / 1_000_000

ROOT       = Path(__file__).parent
SAMPLE_DIR = ROOT.parent / "sample"
OUTPUT_DIR = ROOT.parent / "output"

PDF_PATH = SAMPLE_DIR / "Mesh Reservoir 620k mid.pdf"

# Known page indices (0-based) — confirmed from document
PAGE_SITE_PLAN      = 2   # A100
PAGE_PROPOSED_PLAN  = 5   # A201
PAGE_SUPP_PLAN      = 4   # A200
PAGE_RCP            = 7   # A220

# Scale: 1:100, A3 paper, 1pt = 25.4/72 mm on paper
MM_PER_PT = (25.4 / 72) * 100   # = 35.2778 mm real-world per PDF point

# Ground truth for validation
GT_SITE_AREA     = 527.14
GT_DWELLING      = 198.07
GT_PORCH         = 3.06
GT_OUTDOOR       = 27.18
GT_COVERAGE_PCT  = 41.72
GT_COVERAGE_M2   = 219.91
GT_OVERALL_MM    = 20490

# Cross-validation source (lighting calc, A220) — excludes some areas so delta ~10 m² expected
GT_LIGHTING_DWELLING = 188.48
GT_LIGHTING_PORCH    = 1.98
GT_LIGHTING_OUTDOOR  = 26.57

CALIBRATION_ERROR_THRESHOLD = 0.05   # 5%
AREA_DELTA_FLAG_M2           = 20.0   # flag if dwelling delta > this

# Expected rooms on A201 — type: minimum required count
GT_EXPECTED_ROOMS = {
    "bedroom":      3,
    "wir":          1,
    "ensuite":      1,
    "bathroom":     1,
    "powder_room":  1,
    "laundry":      1,
    "living":       1,
    "kitchen":      1,
    "dining":       1,
    "sitting":      1,
    "entry":        1,
    "porch":        1,
    "study":        1,
    "pantry":       1,
    "outdoor_living": 1,
}

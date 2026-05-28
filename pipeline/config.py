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

PDF_PATH   = SAMPLE_DIR / "DMP Elm Northcote 750k.pdf"
OUTPUT_DIR = ROOT.parent / "output" / PDF_PATH.stem

# Known page indices (0-based) — confirmed from document
PAGE_SITE_PLAN      = 2   # A100
PAGE_PROPOSED_PLAN  = 5   # A201
PAGE_SUPP_PLAN      = 4   # A200
PAGE_RCP            = 7   # A220

# Scale: 1:100, A3 paper, 1pt = 25.4/72 mm on paper
MM_PER_PT = (25.4 / 72) * 100   # = 35.2778 mm real-world per PDF point

# Ground truth for validation — set to None when unknown; checks are skipped for None values
GT_SITE_AREA     = None
GT_DWELLING      = None
GT_PORCH         = None
GT_OUTDOOR       = None
GT_COVERAGE_PCT  = None
GT_COVERAGE_M2   = None
GT_OVERALL_MM    = None   # plan overall length used for calibration; None → use largest dim string

# Cross-validation source (A220 lighting calc) — None when unknown
GT_LIGHTING_DWELLING = None
GT_LIGHTING_PORCH    = None
GT_LIGHTING_OUTDOOR  = None

CALIBRATION_ERROR_THRESHOLD = 0.05   # 5%
AREA_DELTA_FLAG_M2           = 20.0   # flag if dwelling delta > this

# Expected rooms — empty dict skips the room-completeness check
GT_EXPECTED_ROOMS = {}

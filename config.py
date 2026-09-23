import os

# ==========================================
# CONFIGURATION
# ==========================================
API_BASE_URL = "http://localhost:8013/v1"
MODEL_NAME = "gemma-3-1b-it"

# CV_FOLDER = "/run/media/sat-naing-tun/Data/SNT/latex/SNT_CV"
CV_FOLDER = "./test_folder"
OUTPUT_FOLDER = "./output"
OUTPUT_BASENAME = "cv"
COVERLETTER_FOLDER = "./coverletter_templates"
OUTPUT_COVERLETTER_BASENAME = "CoverLetter"
DB_NAME="profile.sqlite"
DATA_FOLDER="./data"

PROFILE_CACHE_FILE = os.path.join(OUTPUT_FOLDER, "user_profile.json")
JOB_CACHE_FILE = os.path.join(OUTPUT_FOLDER, "job_descriptions.json")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}

IGNORE_FOLDERS = [
    ".git",
    ".vscode",
    ".idea",
    ".github",
    "output",
    "venv",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "Recommendations",
]

SIMPLE_SECTIONS_TO_TAILOR = [
    "Professional Summary",
    "Technical Skills",
    "Selected Projects",
]
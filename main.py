import argparse
import os
import sys
from tqdm import tqdm

from config import (
    CV_FOLDER,
    OUTPUT_BASENAME,
    OUTPUT_COVERLETTER_BASENAME,
    OUTPUT_FOLDER,
)

# Imports from existing modules
from generate_cv import generate_tailored_cv
from generate_coverletter import generate_tailored_coverletter
from profile_manager import select_optimal_cv_file
from utils import extract_text_from_file, get_job_description


def get_output_path(basename: str) -> str:
    """Helper to ensure output path has .tex extension in OUTPUT_FOLDER."""
    base = os.path.splitext(basename)[0] if basename.endswith(".tex") else basename
    return os.path.join(OUTPUT_FOLDER, f"{base}.tex")


def main():
    parser = argparse.ArgumentParser(
        description="Generate tailored CV, Cover Letter, or both from a Job Description."
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["both", "cv", "coverletter"],
        default="both",
        help="Target deliverable to generate (default: both).",
    )
    parser.add_argument(
        "-j",
        "--jd",
        type=str,
        help="Job Description text, file path, or URL. If omitted, prompts for input once.",
    )
    parser.add_argument(
        "-c",
        "--cv",
        type=str,
        help="Path to candidate CV file. If omitted, auto-selects best CV from CV_FOLDER.",
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # 1. OBTAIN JOB DESCRIPTION (ONCE)
    # ---------------------------------------------------------
    raw_jd_input = args.jd

    if not raw_jd_input:
        print("=" * 65)
        print("[Step 1] Enter Job Description (URL, file path, or paste multi-line text).")
        print("When finished, press Ctrl+D (or Ctrl+Z on Windows):")
        print("=" * 65)
        raw_jd_input = sys.stdin.read().strip()

    if not raw_jd_input:
        print("[!] No job description provided. Exiting.")
        sys.exit(1)

    print("\n[+] Processing Job Description...")
    job_description = get_job_description(raw_jd_input)
    print(f"[✓] Job Description ready ({len(job_description)} characters).")

    # ---------------------------------------------------------
    # 2. SELECT & READ CANDIDATE CV (ONCE)
    # ---------------------------------------------------------
    cv_file = args.cv
    if not cv_file:
        print("\n[+] Auto-selecting best matching CV from repository...")
        cv_file = select_optimal_cv_file(CV_FOLDER, job_description)

    print(f"[✓] Using CV template: {os.path.basename(cv_file)}")
    candidate_cv_text = extract_text_from_file(cv_file)

    # ---------------------------------------------------------
    # 3. EXECUTE GENERATION (BASED ON MODE)
    # ---------------------------------------------------------
    mode = args.mode.lower()
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    cv_tex_path = get_output_path(OUTPUT_BASENAME)
    cl_tex_path = get_output_path(OUTPUT_COVERLETTER_BASENAME)

    print("\n" + "=" * 65)
    print(f"   STARTING PIPELINE — TARGET MODE: [{mode.upper()}]")
    print("=" * 65)

    if mode in ["cv", "both"]:
        print("\n=== [1/2] GENERATING TAILORED CV ===")
        try:
            generate_tailored_cv(cv_file, job_description, cv_tex_path)
            print(f"[✓] Tailored CV generation finished.")
        except Exception as e:
            print(f"[!] Error during CV generation: {e}")

    if mode in ["coverletter", "both"]:
        print("\n=== [2/2] GENERATING TAILORED COVER LETTER ===")
        try:
            generate_tailored_coverletter(
                raw_job_input=job_description,
                candidate_cv_text=candidate_cv_text,
                output_path=cl_tex_path,
            )
            print(f"[✓] Cover Letter generation finished.")
        except Exception as e:
            print(f"[!] Error during Cover Letter generation: {e}")

    print("\n" + "=" * 65)
    print("   [✓] PIPELINE COMPLETED SUCCESSFULLY")
    print(f"   Outputs saved to: {os.path.abspath(OUTPUT_FOLDER)}")
    print("=" * 65)


if __name__ == "__main__":
    main()
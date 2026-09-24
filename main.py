import argparse
import os

from config import (
    CV_FOLDER,
    OUTPUT_BASENAME,
    OUTPUT_COVERLETTER_BASENAME,
    OUTPUT_FOLDER,
    DATA_FOLDER,
    DB_NAME,
    RESUME_FORMAT,
)
from job_manager import get_or_cache_job_description
from cv_parser import select_optimal_cv_file, build_sqlite_master_profile
from db_manager import SQLiteCRUD
from utils import (
    format_job_summary,
    prompt_for_job_description,
)

# Imported core generation functions
from generate_cv import generate_tailored_cv as generate_cv
from generate_coverletter import generate_tailored_coverletter as generate_cover_letter


def load_full_profile_data() -> dict:
    """Loads all profile attributes from SQLite database."""
    db_path = os.path.join(DATA_FOLDER, DB_NAME)
    if not os.path.exists(db_path):
        build_sqlite_master_profile(cv_folder=CV_FOLDER)
    
    db = SQLiteCRUD(db_path)
    data = {
        "contact": db.get_contact_info(),
        "summary": db.get_summary(),
        "education": db.get_education(),
        "experience": db.get_experience(),
        "projects": db.get_projects(),
        "certifications": db.get_certifications(),
        "languages": db.get_languages(),
        "core_competencies": db.get_core_competencies(),
        "technical_skills": db.get_technical_skills()
    }
    db.close()
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Unified Application Pipeline: Generate tailored CV, Cover Letter, or both simultaneously."
    )
    parser.add_argument(
        "--cv-only",
        action="store_true",
        help="Generate only the tailored CV/Resume."
    )
    parser.add_argument(
        "--cl-only",
        action="store_true",
        help="Generate only the tailored Cover Letter."
    )
    parser.add_argument(
        "--job",
        type=str,
        default="",
        help="Optional direct job description string or text source."
    )
    
    args = parser.parse_args()

    # Determine execution flow (default: both if neither flag is specified)
    generate_cv_flag = True
    generate_cl_flag = True

    if args.cv_only and not args.cl_only:
        generate_cl_flag = False
    elif args.cl_only and not args.cv_only:
        generate_cv_flag = False

    print("=====================================================================")
    print("🚀 Initializing Unified Application Generation Pipeline")
    print(f"   Mode -> CV: {generate_cv_flag} | Cover Letter: {generate_cl_flag}")
    print("=====================================================================")

    # Shared analysis/fetching step (runs only once)
    raw_input = args.job if args.job else prompt_for_job_description()
    job_info = get_or_cache_job_description(raw_input)
    job_summary_str = format_job_summary(job_info)

    print("\n[+] Loading candidate master profile from SQLite...")
    profile_data = load_full_profile_data()

    # 1. Conditionally invoke CV generation function
    if generate_cv_flag:
        selected_template = select_optimal_cv_file(CV_FOLDER)
        base_cv_name = (
            os.path.splitext(OUTPUT_BASENAME)[0]
            if OUTPUT_BASENAME.endswith(".tex")
            else OUTPUT_BASENAME
        )
        output_cv_tex = os.path.join(OUTPUT_FOLDER, f"{base_cv_name}.tex")
        
        # Calls generate_tailored_cv from generate_cv_2.py
        generate_cv(selected_template, job_info, output_cv_tex)

    # 2. Conditionally invoke Cover Letter generation function
    if generate_cl_flag:
        base_cl_name = (
            os.path.splitext(OUTPUT_COVERLETTER_BASENAME)[0]
            if OUTPUT_COVERLETTER_BASENAME.endswith(".tex")
            else OUTPUT_COVERLETTER_BASENAME
        )
        output_cl_tex = os.path.join(OUTPUT_FOLDER, f"{base_cl_name}.tex")
        
        # Calls generate_tailored_coverletter from generate_coverletter_4.py
        generate_cover_letter(raw_input, output_cl_tex)

    print("\n=====================================================================")
    print("[✓] Pipeline execution finished successfully!")
    print("=====================================================================")
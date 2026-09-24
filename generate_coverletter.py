import glob
import json
import os
import re
import sys
from typing import Dict, List
from tqdm import tqdm
from config import (
    CV_FOLDER,
    MODEL_NAME,
    OUTPUT_COVERLETTER_BASENAME,
    OUTPUT_FOLDER,
    DATA_FOLDER,
    DB_NAME,
)
from job_manager import get_or_cache_job_description
from latex_utils import strip_section_headers
from llm_client import client
from cv_parser import select_optimal_cv_file, build_sqlite_master_profile
from db_manager import SQLiteCRUD
from utils import compile_latex_to_pdf, extract_text_from_file, get_job_description


def clean_coverletter_prose(text: str) -> str:
    """Strips remaining preambles, bracketed placeholders, and normalizes spacing."""
    if not text:
        return ""
        
    text = re.sub(r"^```(?:json|latex)?\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```$", "", text).strip()

    # Strip bracketed template placeholders (e.g., [Insert Company's...])
    text = re.sub(r"\[\s*(?:Insert|Fill|Company's?)[^\]]*\]", "", text, flags=re.IGNORECASE)

    text = re.sub(
        r"^(?:Okay|Sure|Certainly|Here\s+is|Here\'s|Below\s+is|This\s+is)[^:]*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    return text.strip()


def get_candidate_profile_from_sqlite() -> Dict[str, any]:
    """Queries candidate metadata and profile data directly from the SQLite database."""
    db_path = os.path.join(DATA_FOLDER, DB_NAME)
    if not os.path.exists(db_path):
        build_sqlite_master_profile(cv_folder=CV_FOLDER)
    
    db = SQLiteCRUD(db_path)
    contact = db.get_contact_info()
    education = db.get_education()
    experience = db.get_experience()
    projects = db.get_projects()
    db.close()
    
    return {
        "contact": contact,
        "education": education,
        "experience": experience,
        "projects": projects
    }


def generate_tailored_coverletter_paragraphs(job_summary_str: str, profile_data: Dict[str, any]) -> Dict[str, str]:
    """Extracts factual milestones from the SQLite profile data and writes a strictly accurate 3-paragraph cover letter."""
    system_prompt = (
        "You are an expert executive cover letter writer. Write a cohesive, highly tailored 3-paragraph cover letter "
        "by pulling ONLY factual timeline data and actual experience from the provided candidate database profile against the target job description.\n"
        "STRICT REQUIREMENTS:\n"
        "1. Write strictly in FIRST-PERSON ('I', 'my'). NEVER use third-person pronouns or refer to yourself by name in the text body.\n"
        "2. ABSOLUTE FACTUAL ACCURACY: Do not mix up job roles, institutions, or projects. Accurately represent your actual background (e.g., specific degree, research at Asian Institute of Technology, work history, and exact technologies used).\n"
        "3. Paragraph Structure:\n"
        "   - paragraph_1: State the exact position applied for, express strong interest, and cite your precise academic/professional background including your exact degree.\n"
        "   - paragraph_2: Detail your direct technical experience and projects from your SQLite profile that align with the job requirements.\n"
        "   - paragraph_3: Conclude with strong alignment to the company's goals and a clear call to action for an interview.\n"
        "4. NO PLACEHOLDERS: Never output bracketed placeholders, template instructions, or notes like '[Insert Company...]'[cite: 1]. Write fully complete sentences.\n"
        "5. Return strictly a JSON object with keys: 'paragraph_1', 'paragraph_2', 'paragraph_3'."
    )

    user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== CANDIDATE PROFILE (SQLITE DATABASE) ===
{json.dumps(profile_data, indent=2)}

INSTRUCTIONS:
Carefully parse the profile data above to ensure exact factual alignment (retaining your correct degree and technical background). Generate the JSON object containing 'paragraph_1', 'paragraph_2', and 'paragraph_3'.
"""

    try:
        response_completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        data = json.loads(response_completion.choices[0].message.content.strip())
        return {
            "paragraph_1": clean_coverletter_prose(data.get("paragraph_1", "")),
            "paragraph_2": clean_coverletter_prose(data.get("paragraph_2", "")),
            "paragraph_3": clean_coverletter_prose(data.get("paragraph_3", ""))
        }
    except Exception as e:
        print(f"[!] Generation error: {e}")
        return {
            "paragraph_1": "I am writing to express my strong interest in this position.",
            "paragraph_2": "My background spans software engineering, system administration, and technical research.",
            "paragraph_3": "I look forward to discussing how my experience can support your team."
        }


def generate_tailored_coverletter(
    raw_job_input: str,
    output_path: str,
    pipeline_pbar: tqdm = None,
) -> str:
    print(f"\n[Step 3] Initializing SQLite Profile Query & Cover Letter Generation...")

    print("[Step 3.1] Querying candidate profile from SQLite...")
    profile_data = get_candidate_profile_from_sqlite()
    contact_data = profile_data.get("contact", {})
    if pipeline_pbar:
        pipeline_pbar.update(1)

    print("[Step 3.2] Extracting and caching job requirements...")
    job_info = get_or_cache_job_description(raw_job_input)
    job_summary_str = format_job_summary(job_info) if 'format_job_summary' in globals() else str(job_info)
    if pipeline_pbar:
        pipeline_pbar.update(1)

    print("[Step 3.3] Comparing SQLite profile against job description via LLM...")
    paragraphs = generate_tailored_coverletter_paragraphs(job_summary_str, profile_data)
    
    from latex_coverletter_writer import LaTeXCoverLetterWriter
    name = contact_data.get("name", "Sat Naing Tun")
    
    # Retrieve email and format as a clickable LaTeX email link instead of location
    email = contact_data.get("email", "")
    email_link = f"\\href{{mailto:{email}}}{{{email}}}" if email else ""

    header_str = LaTeXCoverLetterWriter.extract_header_block(name, contact_data, email_link)
    
    final_tex = LaTeXCoverLetterWriter.build_full_document(
        header_str=header_str,
        body_1_para=paragraphs["paragraph_1"],
        body_2_para=paragraphs["paragraph_2"],
        body_3_para=paragraphs["paragraph_3"],
        sender_name=name
    )

    if pipeline_pbar:
        pipeline_pbar.update(1)

    print(f"\n[Step 3.4] Saving tailored LaTeX cover letter to: {output_path}")
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_tex)
    print("[✓] LaTeX file written successfully.")

    print(f"\n[Step 3.5] Compiling LaTeX to PDF in output directory: {output_dir}")
    compile_latex_to_pdf(output_path, output_dir)
    print("[✓] PDF Compilation step finished.")
    if pipeline_pbar:
        pipeline_pbar.update(1)

    return output_path


if __name__ == "__main__":
    from utils import prompt_for_job_description, format_job_summary
    with tqdm(
        total=4,
        desc="Cover Letter Generation Pipeline",
        unit="stage",
        leave=False,
    ) as pipeline_pbar:
        raw_input = prompt_for_job_description()
        pipeline_pbar.update(1)

        base_filename = (
            os.path.splitext(OUTPUT_COVERLETTER_BASENAME)[0]
            if OUTPUT_COVERLETTER_BASENAME.endswith(".tex")
            else OUTPUT_COVERLETTER_BASENAME
        )
        output_tex_file = os.path.join(OUTPUT_FOLDER, f"{base_filename}.tex")

        generate_tailored_coverletter(
            raw_input,
            output_tex_file,
            pipeline_pbar=pipeline_pbar,
        )

    print("\n=====================================================================")
    print("[✓] Cover letter generation pipeline finished successfully!")
    print("=====================================================================")
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
)
from job_manager import get_or_cache_job_description
from latex_utils import strip_section_headers
from llm_client import client
from cv_parser import select_optimal_cv_file
from utils import compile_latex_to_pdf, extract_text_from_file, get_job_description


def extract_contact_info_from_cv(cv_text: str) -> Dict[str, str]:
    """Uses LLM to reliably extract contact information from CV text."""
    system_prompt = (
        "Extract contact details from the following CV text. Output strictly JSON with keys: "
        '"name", "email", "phone", "location", "linkedin", "github". '
        "If a field is missing, use an empty string."
    )
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": cv_text[:2000]}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content.strip())
        return {
            "name": data.get("name", "tester"),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "location": data.get("location", ""),
            "linkedin": data.get("linkedin", ""),
            "github": data.get("github", "")
        }
    except Exception as e:
        print(f"[!] Metadata extraction fallback: {e}")
        return {
            "name": "tester",
            "email": "test@gmail.com",
            "phone": "09",
            "location": "",
            "linkedin": "https://linkedin.com/in/sat-naing-tun",
            "github": "https://github.com/SatNaingTun"
        }


def clean_coverletter_prose(text: str) -> str:
    """Strips remaining preambles, cleans word spacing, and escapes LaTeX special characters."""
    if not text:
        return ""
        
    text = re.sub(r"^```(?:json|latex)?\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```$", "", text).strip()

    # Remove preambles
    text = re.sub(
        r"^(?:Okay|Sure|Certainly|Here\s+is|Here\'s|Below\s+is|This\s+is)[^:]*:\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Normalize weird concats & spacing
    text = re.sub(r"\[\s*.*?\s*\]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    
    # Escape special LaTeX characters safely
    text = text.replace("&", "\\&").replace("%", "\\%").replace("$", "\\$").replace("#", "\\#")

    return text.strip()


def build_single_page_coverletter_latex(
    candidate_cv_text: str, job_info: Dict[str, str]
) -> str:
    """Generates a fluid 3-paragraph cover letter in a single JSON call for natural flow."""
    contact = extract_contact_info_from_cv(candidate_cv_text)

    company_str = job_info.get("company_name", "your organization")
    if company_str.lower() in ["unknown", "n/a", "none", "", "company"]:
        company_str = "your organization"

    skills_str = ", ".join(job_info.get("required_skills", []))
    job_title = job_info.get("job_title", "Position")

    system_prompt = (
        "You are an expert executive cover letter writer. Write a cohesive, natural 3-paragraph cover letter.\n"
        "STRICT REQUIREMENTS:\n"
        "1. Write strictly in FIRST-PERSON ('I', 'my'). NEVER use third-person pronouns ('he', 'his') or referring to yourself by name.\n"
        "2. Ensure fluid, elegant narrative transitions connecting Paragraph 1 -> Paragraph 2 -> Paragraph 3.\n"
        "3. GROUND TRUTH ONLY: Use real details from CV (e.g. Master of Engineering at Asian Institute of Technology, IT Administrator at Best Oil Company, Research Intern at NII). Never invent fake placeholder company names like XYZ Corp.\n"
        "4. DO NOT output any LaTeX code, headers, or bullet points in the JSON prose values.\n"
        "5. Return strictly JSON with keys: 'paragraph_1', 'paragraph_2', 'paragraph_3'."
    )

    user_prompt = f"""=== CANDIDATE CV GROUND TRUTH ===
{candidate_cv_text}

=== TARGET JOB DETAILS ===
Position: {job_title}
Company: {company_str}
Required Skills: {skills_str}

=== STRUCTURE INSTRUCTIONS ===
- paragraph_1: Warm self-introduction combining my IoT Master's degree at AIT, my enthusiasm for the {job_title} role at {company_str}, and a high-level summary of my background in IT operations and software engineering.
- paragraph_2: Detail my practical technical accomplishments (e.g., leading IT operations at Best Oil Company, developing C#/.NET tools, and AI network research at NII) and connect them smoothly to {skills_str}.
- paragraph_3: Smoothly transition from those technical achievements into how my problem-solving ability ensures operational continuity and system reliability for {company_str}, ending with a confident request for an interview.
"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content.strip())
        p1 = clean_coverletter_prose(data.get("paragraph_1", ""))
        p2 = clean_coverletter_prose(data.get("paragraph_2", ""))
        p3 = clean_coverletter_prose(data.get("paragraph_3", ""))
    except Exception as e:
        print(f"[!] Generation error: {e}")
        p1 = f"I am writing to express my strong interest in the {job_title} position at {company_str}."
        p2 = "My experience spans IT administration and software engineering, including managing critical systems and conducting network research."
        p3 = "I look forward to discussing how my experience can support your team."

    contact_line_1 = []
    if contact.get("email"):
        contact_line_1.append(
            f"Email: \\href{{mailto:{contact['email']}}}{{{contact['email']}}}"
        )
    if contact.get("phone"):
        contact_line_1.append(f"Phone: {contact['phone']}")

    contact_line_2 = []
    if contact.get("linkedin"):
        clean_li = contact["linkedin"].replace("https://", "").replace("http://", "")
        contact_line_2.append(f"LinkedIn: \\href{{{contact['linkedin']}}}{{{clean_li}}}")
    if contact.get("github"):
        clean_gh = contact["github"].replace("https://", "").replace("http://", "")
        contact_line_2.append(f"GitHub: \\href{{{contact['github']}}}{{{clean_gh}}}")

    line1_str = " \\,|\\, ".join(contact_line_1)
    line2_str = " \\,|\\, ".join(contact_line_2)

    header_lines = [f"{{\\Large \\textbf{{{contact['name']}}}}}\\"]
    if contact.get("location"):
        header_lines.append(f"{contact['location']} \\\\")
    if line1_str:
        header_lines.append(f"{line1_str} \\\\")
    if line2_str:
        header_lines.append(f"{line2_str}")

    header_str = "\n".join(header_lines)

    latex_document = f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[margin=0.75in]{{geometry}}
\\usepackage{{hyperref}}
\\usepackage{{parskip}}

\\hypersetup{{
    colorlinks=true,
    linkcolor=blue,
    urlcolor=blue
}}

\\begin{{document}}

\\pagestyle{{empty}}

% Header Block
{header_str}

\\vspace{{1.2em}}

\\today

\\vspace{{1em}}

Dear Hiring Manager,

\\vspace{{0.5em}}

{p1}

\\vspace{{0.8em}}

{p2}

\\vspace{{0.8em}}

{p3}

\\vspace{{1.5em}}

Sincerely,

\\vspace{{1.5em}}

{contact['name']}

\\end{{document}}
"""
    return latex_document


def generate_tailored_coverletter(
    raw_job_input: str,
    candidate_cv_text: str,
    output_path: str,
    pipeline_pbar: tqdm = None,
) -> str:
    print(f"\n[Step 3] Initializing Cover Letter Generation...")

    print("[Step 3.1] Extracting structured details from job description...")
    job_info = get_or_cache_job_description(raw_job_input)

    final_tex = build_single_page_coverletter_latex(candidate_cv_text, job_info)
    if pipeline_pbar:
        pipeline_pbar.update(1)

    print(f"\n[Step 3.2] Saving tailored LaTeX file to: {output_path}")
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_tex)
    print("[✓] LaTeX file written successfully.")

    print(f"\n[Step 3.3] Compiling LaTeX to PDF in output directory: {output_dir}")
    compile_latex_to_pdf(output_path, output_dir)
    print("[✓] PDF Compilation step finished.")
    if pipeline_pbar:
        pipeline_pbar.update(1)

    return output_path


if __name__ == "__main__":
    print("=====================================================================")
    print("[Step 1] Reading Job Description input from terminal...")
    print("Enter Job Description (URL, file path, or paste multi-line text).")
    print("When finished, press Ctrl+D (or Ctrl+Z on Windows):")
    print("=====================================================================")
    user_input = sys.stdin.read().strip()

    if not user_input:
        print("[!] No job description provided. Exiting.")
        exit(1)

    with tqdm(
        total=4,
        desc="Overall Generation Pipeline",
        unit="stage",
        leave=False,
    ) as pipeline_pbar:
        raw_job_text = get_job_description(user_input)
        print(f"\n[✓] Extracted {len(raw_job_text)} characters of job description text.")
        pipeline_pbar.update(1)

        print("\n[Step 2] Locating candidate CV in CV_FOLDER...")
        candidate_cv_file = select_optimal_cv_file(CV_FOLDER, raw_job_text)
        candidate_cv_text = extract_text_from_file(candidate_cv_file)
        print(f"[✓] Extracted {len(candidate_cv_text)} characters from Candidate CV.")
        pipeline_pbar.update(1)

        base_filename = (
            os.path.splitext(OUTPUT_COVERLETTER_BASENAME)[0]
            if OUTPUT_COVERLETTER_BASENAME.endswith(".tex")
            else OUTPUT_COVERLETTER_BASENAME
        )
        output_tex_file = os.path.join(OUTPUT_FOLDER, f"{base_filename}.tex")

        generate_tailored_coverletter(
            raw_job_text,
            candidate_cv_text,
            output_tex_file,
            pipeline_pbar=pipeline_pbar,
        )

    print("\n=====================================================================")
    print("[✓] Cover letter generation pipeline finished successfully!")
    print("=====================================================================")
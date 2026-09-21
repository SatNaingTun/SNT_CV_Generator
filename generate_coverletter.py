import glob
import json
import os
import re
import sys
from typing import Dict, List
from tqdm import tqdm
from config import (
    COVERLETTER_FOLDER,
    CV_FOLDER,
    MODEL_NAME,
    OUTPUT_COVERLETTER_BASENAME,
    OUTPUT_FOLDER,
)
from job_manager import get_or_cache_job_description
from latex_utils import strip_section_headers
from llm_client import client
from profile_manager import select_optimal_cv_file
from utils import compile_latex_to_pdf, extract_text_from_file, get_job_description


def select_optimal_coverletter_file(
    folder_path: str, job_description: str
) -> str:
  """Finds cover letter templates, presents options, and allows interactive user selection."""
  print(f"[Step 3.1] Searching for Cover Letter templates in: {folder_path}")
  target_folder = (
      folder_path
      if os.path.exists(folder_path) and os.listdir(folder_path)
      else CV_FOLDER
  )

  raw_files = glob.glob(os.path.join(target_folder, "*.tex")) + glob.glob(
      os.path.join(target_folder, "*.pdf")
  )

  cl_files = [
      f
      for f in raw_files
      if "coverletter" in os.path.basename(f).lower()
      or "cover_letter" in os.path.basename(f).lower()
  ]
  candidate_files = cl_files if cl_files else raw_files

  if not candidate_files:
    raise FileNotFoundError(
        f"No .tex or .pdf cover letter templates found in {target_folder}"
    )

  filenames = [os.path.basename(f) for f in candidate_files]
  file_map = {os.path.basename(f): f for f in candidate_files}

  print(f"\n[Step 3.2] Found {len(filenames)} candidate template(s):")
  for idx, fname in enumerate(filenames, 1):
    print(f"  {idx:2d}. {fname}")

  print(f"\nDefault selected template: [{filenames[0]}]")
  user_choice = input(
      f"Press [ENTER] to use default template, or enter number (1-"
      f"{len(filenames)}) / filename to override: "
  ).strip()

  if not user_choice:
    selected = file_map[filenames[0]]
  elif user_choice.isdigit() and 1 <= int(user_choice) <= len(filenames):
    selected = file_map[filenames[int(user_choice) - 1]]
  elif user_choice in file_map:
    selected = file_map[user_choice]
  else:
    matching = [
        fpath
        for fname, fpath in file_map.items()
        if user_choice.lower() in fname.lower()
    ]
    if matching:
      selected = matching[0]
    else:
      print(f"[!] Input unrecognized. Defaulting to template: {filenames[0]}")
      selected = file_map[filenames[0]]

  print(f"[Step 3.3] Selected Template: {os.path.basename(selected)}")
  return selected


def clean_coverletter_prose(text: str) -> str:
  """Strips conversational preambles, section headers, bullet lists, and placeholder tags."""
  # 1. Remove markdown code blocks
  text = re.sub(r"^```(?:latex)?\n?", "", text, flags=re.IGNORECASE)
  text = re.sub(r"\n?```$", "", text).strip()

  # 2. Remove conversational intro chatter (e.g., "Okay, here's...", "Here is...")
  text = re.sub(
      r"^(?:Okay|Sure|Certainly|Here\s+is|Here\'s|Below\s+is|This\s+is)[^:]*:\s*",
      "",
      text,
      flags=re.IGNORECASE,
  )

  # 3. Strip surrounding quotes if wrapped
  text = text.strip()
  if (text.startswith('"') and text.endswith('"')) or (
      text.startswith("'") and text.endswith("'")
  ):
    text = text[1:-1].strip()

  # 4. Remove section headers, bullet point tags, and titles
  text = re.sub(
      r"^\s*(?:Core Competencies|Key Qualifications|Skills|Paragraph\s*\d+):?\s*",
      "",
      text,
      flags=re.IGNORECASE | re.MULTILINE,
  )
  text = re.sub(
      r"\[\s*leftmargin\s*=\s*\*?\s*\]", "", text, flags=re.IGNORECASE
  )
  text = re.sub(r"^\s*[\bullet•\-\*]\s*", "", text, flags=re.MULTILINE)
  text = re.sub(r"^\s*\\item\s*", "", text, flags=re.MULTILINE)

  # 5. Remove bracketed placeholders like [mention ...] or [Platform ...]
  text = re.sub(
      r",?\s*particularly in\s*\[\s*mention\s+[^\]]*\]",
      "",
      text,
      flags=re.IGNORECASE,
  )
  text = re.sub(
      r"\[\s*(?:mention|insert|select|specify)\s+[^\]]*\]",
      "",
      text,
      flags=re.IGNORECASE,
  )
  text = re.sub(
      r"\[\s*.*?platform.*?\s*\]", "", text, flags=re.IGNORECASE
  )

  # 6. Clean up spacing and punctuation
  text = re.sub(r"\s{2,}", " ", text)
  text = re.sub(r"\s+\.", ".", text)
  text = re.sub(r"\s+,", ",", text)
  text = re.sub(r",\s*,", ",", text)

  return text.strip()


def build_single_page_coverletter_latex(
    candidate_cv_text: str, job_info: Dict[str, str]
) -> str:
  """Generates 3 distinct cover letter paragraphs using a tqdm loop, then formats them into LaTeX."""
  print("\n[Step 5.2] Generating cover letter paragraphs...")

  company_str = job_info.get("company_name", "your organization")
  if company_str.lower() in ["unknown", "n/a", "none"]:
    company_str = "your organization"

  skills_str = ", ".join(job_info.get("required_skills", []))
  job_title = job_info.get("job_title", "System Analyst")

  paragraph_tasks = [
      (
          "Opening Paragraph",
          (
              f"Write a sincere 2-3 sentence opening paragraph expressing strong"
              f" enthusiasm for the {job_title} role at {company_str}."
              " Introduce your current background as a Master's student in IoT"
              " Engineering at AIT and past IT Administrator experience."
          ),
      ),
      (
          "Experience Alignment Paragraph",
          (
              "Write a single 3-4 sentence body paragraph connecting your"
              " Master's degree from AIT and IT experience at Best Oil Company"
              f" directly to position requirements: {skills_str}. Do NOT write"
              " bullet points or headers."
          ),
      ),
      (
          "Value & Closing Paragraph",
          (
              "Write a 2-3 sentence closing paragraph highlighting your"
              " analytical problem-solving skills, teamwork, and a confident"
              " call-to-action requesting an interview."
          ),
      ),
  ]

  generated_paras = []

  # Iterating with tqdm over the list of paragraph tasks (leave=False hides the bar after completion)
  for title, prompt_desc in tqdm(
      paragraph_tasks,
      desc="[Step 5.2] Processing Paragraphs",
      unit="paragraph",
      leave=False,
  ):
    system_prompt = (
        "CRITICAL INSTRUCTIONS:\n"
        "1. Output ONLY the raw prose paragraph text. Start directly with the first word.\n"
        "2. Absolutely NO conversational preambles (do NOT say 'Okay, here is...', 'Sure, here is...').\n"
        "3. Absolutely NO bullet points, NO lists, NO section titles (e.g. 'Core Competencies'), and NO quotation marks.\n"
        "4. Absolutely NO bracketed placeholders (e.g., do NOT write '[mention a project]').\n"
        "5. Ground all experience strictly in candidate CV facts."
    )
    user_prompt = f"""=== CANDIDATE CV GROUND TRUTH ===
{candidate_cv_text[:3000]}

=== TARGET JOB DETAILS ===
Position: {job_title}
Company: {company_str}

=== PARAGRAPH SPECIFIC TASK ({title}) ===
{prompt_desc}
"""
    try:
      response = client.chat.completions.create(
          model=MODEL_NAME,
          messages=[
              {"role": "system", "content": system_prompt},
              {"role": "user", "content": user_prompt},
          ],
          temperature=0.2,
          max_tokens=300,
      )
      raw_text = response.choices[0].message.content.strip()
      clean_p = clean_coverletter_prose(strip_section_headers(raw_text))
      generated_paras.append(clean_p)
    except Exception as e:
      print(f"[!] Error generating {title}: {e}")
      generated_paras.append(
          f"I am writing to express my strong interest in the {job_title}"
          f" position at {company_str}."
      )

  body_1_para = generated_paras[0] if len(generated_paras) > 0 else ""
  body_2_para = generated_paras[1] if len(generated_paras) > 1 else ""
  body_3_para = generated_paras[2] if len(generated_paras) > 2 else ""

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

% Header / Contact Info
{{\\Large \\textbf{{Sat Naing Tun}}}} \\\\
Bangkok, Thailand \\\\
Email: \\href{{mailto:satnaingtun.snt@gmail.com}}{{satnaingtun.snt@gmail.com}} \\,|\\, Phone: +66 961540370 \\\\
LinkedIn: \\href{{https://linkedin.com/in/satnaingtun}}{{linkedin.com/in/satnaingtun}} \\,|\\, GitHub: \\href{{https://github.com/SatNaingTun}}{{github.com/SatNaingTun}}

\\vspace{{1.2em}}

\\today

\\vspace{{1em}}

Dear Hiring Manager,

\\vspace{{0.5em}}

{body_1_para}

\\vspace{{0.8em}}

{body_2_para}

\\vspace{{0.8em}}

{body_3_para}

\\vspace{{1.5em}}

Sincerely,

\\vspace{{1.5em}}

Sat Naing Tun

\\end{{document}}
"""
  return latex_document


def generate_tailored_coverletter(
    template_path: str,
    raw_job_input: str,
    candidate_cv_text: str,
    output_path: str,
    pipeline_pbar: tqdm = None,
) -> str:
  """Main execution pipeline: parses job info, constructs a single-page cover letter, writes LaTeX, and compiles to PDF."""
  print(f"\n[Step 5] Initializing Cover Letter Generation...")

  # Step 5.1: Parse/cache structured job details via LLM
  print("[Step 5.1] Extracting structured details from job description...")
  job_info = get_or_cache_job_description(raw_job_input)

  # Step 5.2: Build clean multi-paragraph cover letter using tqdm loop
  final_tex = build_single_page_coverletter_latex(candidate_cv_text, job_info)
  if pipeline_pbar:
    pipeline_pbar.update(1)

  # Step 5.3: Save LaTeX file
  print(f"\n[Step 5.3] Saving tailored LaTeX file to: {output_path}")
  output_dir = os.path.dirname(output_path)
  os.makedirs(output_dir, exist_ok=True)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(final_tex)
  print("[✓] LaTeX file written successfully.")

  # Step 5.4: Compile LaTeX output into PDF
  print(f"\n[Step 5.4] Compiling LaTeX to PDF in output directory: {output_dir}")
  compile_latex_to_pdf(output_path, output_dir)
  print("[✓] PDF Compilation step finished.")
  if pipeline_pbar:
    pipeline_pbar.update(1)

  return output_path


if __name__ == "__main__":
  # Step 1: Prompt user for multi-line job description input
  print("=====================================================================")
  print("[Step 1] Reading Job Description input from terminal...")
  print("Enter Job Description (URL, file path, or paste multi-line text).")
  print("When finished, press Ctrl+D (or Ctrl+Z on Windows):")
  print("=====================================================================")
  user_input = sys.stdin.read().strip()

  if not user_input:
    print("[!] No job description provided. Exiting.")
    exit(1)

  # Overall Pipeline Progress Bar with leave=False
  with tqdm(
      total=5,
      desc="Overall Generation Pipeline",
      unit="stage",
      leave=False,
  ) as pipeline_pbar:
    # Step 1: Parsing input text
    raw_job_text = get_job_description(user_input)
    print(
        f"\n[✓] Extracted {len(raw_job_text)} characters of job description"
        " text."
    )
    pipeline_pbar.update(1)

    # Step 2: Locating and reading candidate CV
    print("\n[Step 2] Locating candidate CV in CV_FOLDER...")
    candidate_cv_file = select_optimal_cv_file(CV_FOLDER, raw_job_text)
    candidate_cv_text = extract_text_from_file(candidate_cv_file)
    print(
        f"[✓] Extracted {len(candidate_cv_text)} characters from Candidate"
        " CV."
    )
    pipeline_pbar.update(1)

    # Step 3: Interactive cover letter template selection
    print("\n[Step 3] Cover Letter Template Selection...")
    selected_coverletter_template = select_optimal_coverletter_file(
        COVERLETTER_FOLDER, raw_job_text
    )
    pipeline_pbar.update(1)

    # Step 4 & 5: Generate output and compile PDF
    base_filename = (
        os.path.splitext(OUTPUT_COVERLETTER_BASENAME)[0]
        if OUTPUT_COVERLETTER_BASENAME.endswith(".tex")
        else OUTPUT_COVERLETTER_BASENAME
    )
    output_tex_file = os.path.join(OUTPUT_FOLDER, f"{base_filename}.tex")

    generate_tailored_coverletter(
        selected_coverletter_template,
        raw_job_text,
        candidate_cv_text,
        output_tex_file,
        pipeline_pbar=pipeline_pbar,
    )

  print(
      "\n====================================================================="
  )
  print("[✓] Cover letter generation pipeline finished successfully!")
  print(
      "====================================================================="
  )
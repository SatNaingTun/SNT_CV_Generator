#!/usr/bin/env python3
"""
Section & Entry-Level Tailored LaTeX CV Generator
Uses local llama.cpp server (Gemma 3 1B) via OpenAI-compatible API endpoint.

Key Features:
- Uses sys.stdin.read() for multi-line input (Requires [ENTER] then [Ctrl+D]).
- Processes 'PROFESSIONAL EXPERIENCE' company-by-company to prevent dropping company names/dates.
- Copies image assets (.png, .jpg, .jpeg, .svg, .webp, .gif) and asset directories (e.g., photos/).
- Prevents section header duplication by stripping echoed \section{} titles.
- Sanitizes LaTeX special characters (C#, &, %, #).
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# ==========================================
# CONFIGURATION
# ==========================================
API_BASE_URL = "http://localhost:8013/v1"
MODEL_NAME = "gemma-3-1b-it"

CV_FOLDER = "/run/media/sat-naing-tun/Data/SNT/latex/SNT_CV"
OUTPUT_DIR = "./output"
OUTPUT_BASENAME = "cv"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}

# Non-experience sections tailored as whole blocks
SIMPLE_SECTIONS_TO_TAILOR = [
    "Professional Summary",
    "Technical Skills",
    "Selected Projects",
]

# Initialize OpenAI client pointing to local llama.cpp server
client = OpenAI(base_url=API_BASE_URL, api_key="not-needed")

def copy_cv_assets(
    cv_folder: str,
    output_dir: str,
    ignore_folders: list = None,
):
  """Copy image files and subdirectories (e.g., photos/) to output directory,

  skipping folders specified in ignore_folders.
  """
  if ignore_folders is None:
    ignore_folders = [
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

  print(f"[+] Copying image assets from {cv_folder} to {output_dir}...")

  for item in os.listdir(cv_folder):
    # Skip folders/files explicitly listed in ignore_folders
    if item in ignore_folders:
      continue

    src_path = os.path.join(cv_folder, item)
    dst_path = os.path.join(output_dir, item)

    ext = os.path.splitext(item)[1].lower()

    if os.path.isdir(src_path):
      if os.path.exists(dst_path):
        shutil.rmtree(dst_path)

      # Copy directory while preventing nested ignored directories from copying over
      shutil.copytree(
          src_path,
          dst_path,
          ignore=shutil.ignore_patterns(*ignore_folders, "*.pyc"),
      )
    elif os.path.isfile(src_path) and ext in IMAGE_EXTENSIONS:
      shutil.copy2(src_path, dst_path)


def sanitize_latex_characters(text: str) -> str:
  """Sanitize LaTeX special characters produced by LLM.

  Ensures C#, &, %, # are properly escaped with a single backslash (e.g. C\#),
  and converts double-escaped backslashes (C\\#) to single backslash (C\#).
  """
  text = text.replace(r"C\\#", r"C\#").replace(r"c\\#", r"C\#")
  text = (
      text.replace(r"\\#", r"\#")
      .replace(r"\\&", r"\&")
      .replace(r"\\%", r"\%")
  )

  text = re.sub(r"(?<!\\)C#", r"C\\#", text)
  text = re.sub(r"(?<!\\)c#", r"C\\#", text)

  text = re.sub(r"(?<!\\)#", r"\\#", text)
  text = re.sub(r"(?<!\\)&", r"\\&", text)
  text = re.sub(r"(?<!\\)%", r"\\%", text)

  return text


def strip_redundant_section_header(body: str, section_title: str) -> str:
  """Strip any leading \\section{...} or \\section*{...} echoed by the LLM."""
  pattern = r"^\s*\\section\*?\{" + re.escape(section_title) + r"\}\s*"
  body = re.sub(pattern, "", body, flags=re.IGNORECASE).strip()

  body = re.sub(
      r"^\s*\\section\*?\{[^}]+\}\s*", "", body, flags=re.IGNORECASE
  ).strip()
  return body


def get_job_description(input_str: str) -> str:
  """Fetch job posting text from a URL, local file path, or raw text."""
  clean_input = input_str.strip()

  if os.path.isfile(clean_input):
    print(f"[+] Reading job description from file: {clean_input}")
    with open(clean_input, "r", encoding="utf-8", errors="ignore") as f:
      return f.read().strip()

  if clean_input.startswith("http://") or clean_input.startswith("https://"):
    print(f"[+] Scraping job URL: {clean_input}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(clean_input, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for script in soup(["script", "style", "nav", "footer"]):
      script.decompose()
    return soup.get_text(separator=" ", strip=True)

  return clean_input


def find_best_cv_file(folder_path: str, job_description: str) -> str:
  """Find the best matching LaTeX CV template based on job posting keywords."""
  files = glob.glob(os.path.join(folder_path, "*.tex"))
  if not files:
    raise FileNotFoundError(f"No .tex templates found in {folder_path}")

  job_desc_lower = job_description.lower()
  best_file = files[0]
  best_score = -1

  for filepath in files:
    score = 0
    filename = os.path.basename(filepath).lower()

    if (
        "analyst" in job_desc_lower
        or "support" in job_desc_lower
        or "system" in job_desc_lower
    ) and "it_support" in filename:
      score += 50
    elif "software" in job_desc_lower and "software" in filename:
      score += 50

    words = re.sub(r"[\._-]", " ", filename).split()
    for w in words:
      if len(w) > 2 and w in job_desc_lower:
        score += 10

    if score > best_score:
      best_score = score
      best_file = filepath

  return best_file


def query_section_llm(
    section_name: str, section_content: str, job_description: str
) -> str:
  """Send a standalone section block to Gemma 3 1B for focused rephrasing."""
  print(f"[+] Tailoring section: '{section_name}'...")

  formatting_rule = ""
  if "skill" in section_name.lower():
    formatting_rule = (
        "\nFORMAT RULE FOR TECHNICAL SKILLS:\n"
        "Must use an \\begin{itemize} ... \\end{itemize} environment. Group"
        " skills cleanly into structured bullet points like:\n"
        "\\item \\textbf{Programming Languages:} Python, C\\#, C++, Bash\n"
        "\\item \\textbf{Systems & Cloud:} Linux (Ubuntu), AWS, Terraform,"
        " Docker\n"
    )

  system_prompt = (
      "You are a specialized resume editing engine. Your job is to rewrite"
      " ONLY the provided section body content to align with the target job"
      " description. Do NOT output section headers like \\section{...}. Output"
      " ONLY the section body content."
  )

  user_prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:2000]}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION LATEX CONTENT ===
{section_content}

=== INSTRUCTIONS ===
1. Rephrase bullet points to emphasize skills, tools, and keywords from the job description.
2. Keep all facts, company names, dates, and degree titles 100% accurate. Do not invent experience.
3. Preserve valid LaTeX syntax (e.g., \\begin{{itemize}}, \\item, \\end{{itemize}}, \\textbf{{}}, \\hfill).
4. Strictly escape special characters in output (e.g., C\\#, \\&, \\%, \\#).
5. DO NOT include the \\section{{{section_name}}} header line in your output.{formatting_rule}

=== OUTPUT UPDATED SECTION LATEX BODY ONLY ===
"""

  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=1500,
    )
    output = response.choices[0].message.content.strip()

    if "```latex" in output:
      output = output.split("```latex")[1].split("```")[0]
    elif "```" in output:
      output = output.split("```")[1].split("```")[0]

    output = strip_redundant_section_header(output.strip(), section_name)
    return sanitize_latex_characters(output)

  except Exception as e:
    print(f"[!] Warning: API request failed for section '{section_name}': {e}")
    return sanitize_latex_characters(section_content)


def query_company_bullets_llm(
    company_context: str, original_bullets: str, job_description: str
) -> str:
  """Send ONLY the bullet points of a single company entry to the small LLM."""
  system_prompt = (
      "You are a resume bullet point editor. Your ONLY job is to rephrase the"
      " itemized bullet points for a single job position to align with the"
      " target job description. Do NOT write company names, job titles, or"
      " dates."
  )

  user_prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:1500]}

=== CONTEXT (COMPANY & ROLE) ===
{company_context}

=== ORIGINAL BULLET POINTS ===
{original_bullets}

=== INSTRUCTIONS ===
1. Rewrite ONLY the \\item bullet points to highlight relevant skills and achievements for the job description.
2. Keep all facts, technologies, and achievements accurate. Do not invent fake experience.
3. Maintain valid LaTeX \\begin{{itemize}} ... \\end{{itemize}} environment structure.
4. Strictly escape special LaTeX characters (C\\#, \\&, \\%, \\#).
5. Output ONLY the updated \\begin{{itemize}} ... \\end{{itemize}} block. Do NOT include company titles or header metadata.

=== OUTPUT UPDATED LATEX BULLETS ONLY ===
"""

  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=800,
    )
    bullets = response.choices[0].message.content.strip()

    if "```latex" in bullets:
      bullets = bullets.split("```latex")[1].split("```")[0]
    elif "```" in bullets:
      bullets = bullets.split("```")[1].split("```")[0]

    return sanitize_latex_characters(bullets.strip())

  except Exception as e:
    print(
        f"[!] Warning: API request failed for company bullets"
        f" ({company_context[:30]}...): {e}"
    )
    return sanitize_latex_characters(original_bullets)


def process_professional_experience_company_by_company(
    experience_body: str, job_description: str
) -> str:
  """Parses individual job entries, keeping Company, Title, and Dates frozen in Python,

  and sending only the bullet points for each company to the LLM.
  """
  entry_pattern = re.compile(
      r'((?:\\textbf\{[^}]+\}|\\subsection\*?\{[^}]+\}|\\bold\{[^}]+\}).*?)'
      r'(\\begin\{itemize\}.*?\\end\{itemize\})',
      re.DOTALL,
  )

  matches = list(entry_pattern.finditer(experience_body))

  if not matches:
    print(
        "[!] Company entry pattern did not match. Falling back to whole-section"
        " processing for Professional Experience."
    )
    return query_section_llm(
        "PROFESSIONAL EXPERIENCE", experience_body, job_description
    )

  updated_body = experience_body
  for match in reversed(matches):
    header_tex = match.group(1)
    bullets_tex = match.group(2)

    header_plain = re.sub(r"\\[a-zA-Z]+\{([^}]+)\}", r"\1", header_tex)
    header_plain = re.sub(r"\s+", " ", header_plain).strip()

    print(f"[+] Processing company entry: {header_plain[:50]}...")
    tailored_bullets = query_company_bullets_llm(
        header_plain, bullets_tex, job_description
    )

    replacement = f"{header_tex}\n{tailored_bullets}"
    start, end = match.span()
    updated_body = updated_body[:start] + replacement + updated_body[end:]

  return updated_body


def update_cv_sections(
    full_tex_content: str, job_description: str
) -> str:
  """Extract, tailor, and re-insert specified sections into master LaTeX template."""
  updated_tex = full_tex_content

  # 1. Process standard sections (Summary, Skills, Projects)
  for section_title in SIMPLE_SECTIONS_TO_TAILOR:
    pattern = re.compile(
        r"(\\section\*?\{"
        + re.escape(section_title)
        + r"\}\s*\n)(.*?)(?=\\section|\n\\end\{document\}|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    match = pattern.search(updated_tex)
    if not match:
      print(f"[!] Section '{section_title}' not found in template. Skipping.")
      continue

    section_header = match.group(1)
    original_body = match.group(2).strip()

    updated_body = query_section_llm(
        section_title, original_body, job_description
    )

    replacement = f"{section_header}\n{updated_body}\n\n"
    updated_tex = (
        updated_tex[: match.start()] + replacement + updated_tex[match.end() :]
    )

  # 2. Process PROFESSIONAL EXPERIENCE company-by-company
  exp_title = "PROFESSIONAL EXPERIENCE"
  exp_pattern = re.compile(
      r"(\\section\*?\{"
      + re.escape(exp_title)
      + r"\}\s*\n)(.*?)(?=\\section|\n\\end\{document\}|\Z)",
      re.DOTALL | re.IGNORECASE,
  )

  exp_match = exp_pattern.search(updated_tex)
  if exp_match:
    section_header = exp_match.group(1)
    original_exp_body = exp_match.group(2).strip()

    print(f"[+] Tailoring section: '{exp_title}' company-by-company...")
    tailored_exp_body = process_professional_experience_company_by_company(
        original_exp_body, job_description
    )

    replacement = f"{section_header}\n{tailored_exp_body}\n\n"
    updated_tex = (
        updated_tex[: exp_match.start()]
        + replacement
        + updated_tex[exp_match.end() :]
    )
  else:
    print(f"[!] Section '{exp_title}' not found in template. Skipping.")

  return updated_tex


def compile_miktex_pdf(tex_filepath: str, output_dir: str):
  """Compile generated LaTeX to PDF using pdflatex."""
  print(f"[+] Compiling assembled LaTeX with pdflatex...")
  try:
    subprocess.run(
        [
            "pdflatex",
            f"-output-directory={output_dir}",
            "-interaction=nonstopmode",
            tex_filepath,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pdf_path = os.path.abspath(os.path.join(output_dir, f"{OUTPUT_BASENAME}.pdf"))
    print(f"[✓] Successfully compiled PDF: {pdf_path}")
  except subprocess.CalledProcessError:
    print(
        "[!] pdflatex compilation encountered errors. Check output/cv.log for"
        " details."
    )


def main():
  os.makedirs(OUTPUT_DIR, exist_ok=True)

  print("==================================================")
  print("   Section & Company-Level LaTeX CV Generator    ")
  print("==================================================")
  print("Paste Job Posting Text, File Path, or URL below.")
  print("When finished, press [ENTER] then [Ctrl+D] on a new line:\n")

  try:
    job_input = sys.stdin.read().strip()
  except KeyboardInterrupt:
    print("\n[!] Cancelled by user.")
    return

  if not job_input:
    print("\n[!] Job description input cannot be empty.")
    return

  job_description = get_job_description(job_input)

  # 1. Match source LaTeX template
  selected_cv_path = find_best_cv_file(CV_FOLDER, job_description)
  print(f"\n[✓] Selected source template: {os.path.basename(selected_cv_path)}")

  # 2. Copy image assets and folders (e.g., photos/)
  copy_cv_assets(CV_FOLDER, OUTPUT_DIR)

  with open(selected_cv_path, "r", encoding="utf-8") as f:
    full_tex = f.read()

  # 3. Process sections and company entries step-by-step
  tailored_tex = update_cv_sections(full_tex, job_description)

  # 4. Save reassembled LaTeX file
  tex_filepath = os.path.join(OUTPUT_DIR, f"{OUTPUT_BASENAME}.tex")
  with open(tex_filepath, "w", encoding="utf-8") as f:
    f.write(tailored_tex)
  print(f"[✓] Saved reassembled LaTeX to: {tex_filepath}")

  # 5. Compile PDF
  compile_miktex_pdf(tex_filepath, OUTPUT_DIR)


if __name__ == "__main__":
  main()
#!/usr/bin/env python3
"""
Section & Entry-Level Tailored LaTeX CV & Cover Letter Generator
Uses local llama.cpp server (Gemma 3 1B) via OpenAI-compatible API endpoint.

Key Features:
- Uses sys.stdin.read() for multi-line input (Requires [ENTER] then [Ctrl+D]).
- Processes 'PROFESSIONAL EXPERIENCE' company-by-company to prevent dropping company names/dates.
- Generates and compiles both cv.pdf and cover_letter.pdf into the output directory.
- Copies image assets (.png, .jpg, .jpeg, .svg, .webp, .gif) and asset directories (e.g., photos/).
- Prevents section header duplication by stripping echoed \section{} titles.
- Sanitizes LaTeX special characters (C#, &, %, #).
"""

import glob
import json
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
    if item in ignore_folders:
      continue

    src_path = os.path.join(cv_folder, item)
    dst_path = os.path.join(output_dir, item)

    ext = os.path.splitext(item)[1].lower()

    if os.path.isdir(src_path):
      if os.path.exists(dst_path):
        shutil.rmtree(dst_path)

      shutil.copytree(
          src_path,
          dst_path,
          ignore=shutil.ignore_patterns(*ignore_folders, "*.pyc"),
      )
    elif os.path.isfile(src_path) and ext in IMAGE_EXTENSIONS:
      shutil.copy2(src_path, dst_path)




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


def compile_latex_to_pdf(tex_filepath: str, output_dir: str) -> str:
  """Compile any generated .tex file to PDF using pdflatex."""
  filename = os.path.basename(tex_filepath)
  file_stem = os.path.splitext(filename)[0]
  expected_pdf = os.path.abspath(os.path.join(output_dir, f"{file_stem}.pdf"))

  print(f"[+] Compiling {filename} to PDF with pdflatex...")
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
    print(f"[✓] Successfully compiled PDF: {expected_pdf}")
    return expected_pdf
  except (subprocess.CalledProcessError, FileNotFoundError) as e:
    print(f"[!] pdflatex compilation failed for {filename}: {e}")
    return ""

def extract_salutation(
    job_description: str, client, model_name: str
) -> str:
  """Extracts or infers the most polite salutation from the job description."""
  prompt = f"""
Analyze the job description below to identify if a specific contact person or hiring manager is named.

=== JOB DESCRIPTION ===
{job_description[:2000]}

=== RULES ===
1. If NO specific contact person is named -> output EXACTLY: Dear Hiring Manager,
2. If titled as Dr. or Prof. -> output e.g.: Dear Dr. [Last Name],
3. If title is explicitly stated (Mr. / Ms.) -> output e.g.: Dear Ms. [Last Name],
4. If a name is given without an explicit title (e.g., "Ananya" or "Ananya Prasert") -> output e.g.: Dear Ananya, or Dear Ananya Prasert,
5. Output ONLY the single salutation line ending with a comma. No quotes, explanations, or extra text.
"""

  try:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract polite email/letter salutations accurately."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=20,
    )
    salutation = response.choices[0].message.content.strip()
    return salutation if salutation else "Dear Hiring Manager,"
  except Exception:
    return "Dear Hiring Manager,"


from typing import Dict, Union


# Optional PDF parser
try:
  import pypdf
except ImportError:
  pypdf = None




def ensure_parent_dir(filepath: str) -> None:
  """Ensures parent directory structure exists."""
  parent_dir = os.path.dirname(filepath)
  if parent_dir:
    os.makedirs(parent_dir, exist_ok=True)


def sanitize_latex_characters(text: str) -> str:
  """Escapes special LaTeX reserved characters in user/LLM text without breaking

  LaTeX command braces {} or double-escaping already escaped characters.
  """
  if not text:
    return ""

  # DO NOT include '{' or '}' as they are required for LaTeX syntax
  # Use negative lookbehind (?<!\\) to avoid double-escaping (e.g., C\# -> C\#)
  replacements = {
      r"(?<!\\)&": r"\&",
      r"(?<!\\)%": r"\%",
      r"(?<!\\)\$": r"\$",
      r"(?<!\\)#": r"\#",
      r"(?<!\\)_": r"\_",
      r"(?<!\\)~": r"\textasciitilde{}",
      r"(?<!\\)\^": r"\textasciicircum{}",
  }

  for pattern, repl in replacements.items():
    text = re.sub(pattern, repl, text)

  return text


def clean_cover_letter_body(body_text: str, candidate_name: str = "") -> str:
  """Post-processes LLM body output to remove duplicate salutations, duplicate

  sign-offs, and bracketed AI placeholders.
  """
  if not body_text:
    return ""

  lines = body_text.strip().split("\n")

  # 1. Strip leading salutations or subject headers generated by LLM
  while lines and (
      re.match(
          r"^(dear|to|re:|subject:|application for)\b",
          lines[0].strip(),
          re.IGNORECASE,
      )
      or not lines[0].strip()
  ):
    lines.pop(0)

  # 2. Strip trailing sign-offs or signature lines generated by LLM
  while lines and (
      re.match(
          r"^(sincerely|yours sincerely|regards|best regards|thanks|thank you),?$",
          lines[-1].strip(),
          re.IGNORECASE,
      )
      or (candidate_name and candidate_name.lower() in lines[-1].lower())
      or not lines[-1].strip()
  ):
    lines.pop()

  text = "\n".join(lines).strip()

  # 3. Clean up generic AI bracketed placeholders
  text = re.sub(
      r"\[(?:Your Phone Number|Your Email Address)[^\]]*\](?:\s*or\s*\[(?:Your Phone Number|Your Email Address)[^\]]*\])?",
      "the contact details listed above",
      text,
      flags=re.IGNORECASE,
  )
  text = re.sub(
      r"\[(?:Platform|where you saw|advertisement)[^\]]*\]",
      "your career portal",
      text,
      flags=re.IGNORECASE,
  )
  text = re.sub(
      r"\[(?:Previous Company Name|Company Name)[^\]]*\]",
      "my previous organization",
      text,
      flags=re.IGNORECASE,
  )
  text = re.sub(
      r"\[(?:Mention specific tools|Briefly describe)[^\]]*\]",
      "",
      text,
      flags=re.IGNORECASE,
  )

  # Remove any remaining raw bracketed text [...]
  text = re.sub(r"\[[^*\]]+\]", "", text)

  # Clean double spaces or orphaned commas caused by bracket stripping
  text = re.sub(r"\s+,", ",", text)
  text = re.sub(r"  +", " ", text)

  return text


def extract_text_from_file(file_path: str) -> str:
  """Extracts plain text content from a .tex, .pdf, or text file path."""
  if not os.path.exists(file_path):
    raise FileNotFoundError(f"File not found: {file_path}")

  ext = os.path.splitext(file_path)[1].lower()

  if ext in [".tex", ".txt", ".md"]:
    with open(file_path, "r", encoding="utf-8") as f:
      return f.read()

  elif ext == ".pdf":
    if pypdf is None:
      raise ImportError(
          "pypdf library is required for PDF parsing: pip install pypdf"
      )
    text_content = []
    with open(file_path, "rb") as f:
      reader = pypdf.PdfReader(f)
      for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
          text_content.append(extracted)
    return "\n".join(text_content).strip()

  raise ValueError(f"Unsupported file format: {ext}")


def extract_candidate_metadata_and_context(
    selected_cv_path: str, job_description: str
) -> Dict[str, Union[str, list]]:
  """Extracts candidate metadata and aligns context strictly from the single chosen CV file."""
  cv_text = extract_text_from_file(selected_cv_path)

  prompt = f"""
You are an expert career consultant. Analyze the candidate's raw CV content and target job description below.

=== RAW CV CONTENT ({os.path.basename(selected_cv_path)}) ===
{cv_text[:3500]}

=== TARGET JOB DESCRIPTION ===
{job_description[:2000]}

=== JSON OUTPUT INSTRUCTIONS ===
Extract candidate details and synthesize context aligned with the target role strictly from the provided CV:
{{
  "full_name": "Full Name extracted from CV",
  "location": "City, Country extracted from CV",
  "phone": "Phone number extracted from CV",
  "email": "Email address extracted from CV",
  "linkedin": "LinkedIn URL extracted from CV",
  "github": "GitHub URL extracted from CV",
  "aligned_context": "Summary of 3-4 key technical skills and 2 relevant project/job achievements from the CV matching the role requirements."
}}
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract structured candidate metadata strictly from the"
                    " provided CV into JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content.strip())
  except Exception as e:
    print(f"[!] Metadata Extraction Error: {e}")
    return {
        "full_name": "Applicant",
        "location": "",
        "phone": "",
        "email": "",
        "linkedin": "",
        "github": "",
        "aligned_context": cv_text[:1000],
    }


def extract_job_metadata(job_description: str) -> Dict[str, str]:
  """Extracts role, company, recipient, and salutation details from job description."""
  prompt = f"""
Extract company and job position details from this job description:
{job_description[:2000]}

JSON Format:
{{
  "job_title": "Target Position Title",
  "company_name": "Company Name",
  "recipient_name": "Hiring Manager Name or 'Hiring Manager'",
  "recipient_title": "Title or 'Talent Acquisition Team'",
  "company_address": "City, Country or 'Company Headquarters'"
}}
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content.strip())
  except Exception as e:
    print(f"[!] Job Metadata Extraction Error: {e}")
    return {
        "job_title": "Position Applied For",
        "company_name": "Hiring Company",
        "recipient_name": "Hiring Manager",
        "recipient_title": "Talent Acquisition Team",
        "company_address": "",
    }


def generate_nus_cover_letter(
    candidate_data: Dict[str, Union[str, list]],
    job_description: str,
    output_dir: str = OUTPUT_DIR,
    compile_pdf: bool = True,
) -> str:
  """Generates an NUS-standard cover letter strictly using pre-extracted candidate_data."""
  os.makedirs(output_dir, exist_ok=True)

  # 1. Extract job metadata
  job_meta = extract_job_metadata(job_description)

  # Determine salutation
  recipient_name = job_meta.get("recipient_name", "").strip()
  if recipient_name and recipient_name.lower() != "hiring manager":
    salutation = f"Dear {recipient_name},"
  else:
    salutation = "Dear Hiring Manager,"

  # 2. Generate 4 formal NUS body paragraphs
  body_prompt = f"""
Write EXACTLY 4 formal body paragraphs following NUS Cover Letter Standards for applicant {candidate_data.get('full_name')}.

=== CANDIDATE DETAILS ===
Name: {candidate_data.get('full_name')}
Email: {candidate_data.get('email')}
Phone: {candidate_data.get('phone')}
Aligned Qualifications: {candidate_data.get('aligned_context')}

=== TARGET POSITION & COMPANY ===
Role: {job_meta.get('job_title')}
Company: {job_meta.get('company_name')}

=== CRITICAL CONSTRAINTS ===
1. NEVER use bracketed placeholders like [Platform], [Company Name], [Your Phone], or [Insert Tool]. Write complete sentences using the real details provided above.
2. DO NOT include greetings (e.g. 'Dear...'), headers, or subject lines.
3. DO NOT include sign-offs (e.g. 'Sincerely', 'Yours sincerely') or candidate name lines at the end.
4. Output EXACTLY 4 body paragraphs separated by double newlines.

=== PARAGRAPH STRUCTURE ===
- Paragraph 1: Express strong interest in the {job_meta.get('job_title')} position at {job_meta.get('company_name')} and state core value proposition.
- Paragraph 2: Detail technical skills directly matching the job requirements.
- Paragraph 3: Highlight achievements in software development, system analysis, or IT operations.
- Paragraph 4: Reiterate enthusiasm, state availability for an interview via the contact details provided, and express gratitude.
"""

  response = client.chat.completions.create(
      model=MODEL_NAME,
      messages=[
          {"role": "system", "content": "You write executive cover letters."},
          {"role": "user", "content": body_prompt},
      ],
      temperature=0.2,
      max_tokens=1000,
  )

  raw_body = response.choices[0].message.content.strip()

  # Clean LLM response (strip duplicates and placeholders)
  cleaned_body = clean_cover_letter_body(
      raw_body, candidate_name=candidate_data.get("full_name", "")
  )

  # Sanitize special characters for LaTeX compilation
  final_latex_body = sanitize_latex_characters(cleaned_body)

  # 3. Construct LaTeX document
  latex_template = r"""\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\usepackage{parskip}

\hypersetup{colorlinks=true, linkcolor=black, urlcolor=blue}

\begin{document}
\pagestyle{empty}

\begin{flushleft}
{\Large \textbf{__APPLICANT_NAME__}} \\
\vspace{0.3em}
__APPLICANT_LOCATION__ \quad $\cdot$ \quad __APPLICANT_PHONE__ \quad $\cdot$ \quad __APPLICANT_EMAIL__ \\
\href{__APPLICANT_LINKEDIN__}{LinkedIn Profile} \quad $\cdot$ \quad \href{__APPLICANT_GITHUB__}{GitHub Profile}
\end{flushleft}

\vspace{0.5em}
\hrule width \textwidth height 0.6pt
\vspace{1.2em}

\today

\vspace{1.2em}

\begin{flushleft}
\textbf{__RECIPIENT_NAME__} \\
__RECIPIENT_TITLE__ \\
__COMPANY_NAME__ \\
__COMPANY_ADDRESS__
\end{flushleft}

\vspace{1.2em}

\textbf{RE: Application for __JOB_TITLE__}

\vspace{1em}

__SALUTATION__

__BODY_CONTENT__

\vspace{1.5em}

Yours sincerely, \\
\vspace{2.5em}

\textbf{__APPLICANT_NAME__}

\end{document}"""

  latex_document = (
      latex_template.replace(
          "__APPLICANT_NAME__",
          sanitize_latex_characters(candidate_data.get("full_name", "")),
      )
      .replace(
          "__APPLICANT_LOCATION__",
          sanitize_latex_characters(candidate_data.get("location", "")),
      )
      .replace(
          "__APPLICANT_PHONE__",
          sanitize_latex_characters(candidate_data.get("phone", "")),
      )
      .replace(
          "__APPLICANT_EMAIL__",
          sanitize_latex_characters(candidate_data.get("email", "")),
      )
      .replace("__APPLICANT_LINKEDIN__", candidate_data.get("linkedin", ""))
      .replace("__APPLICANT_GITHUB__", candidate_data.get("github", ""))
      .replace(
          "__RECIPIENT_NAME__",
          sanitize_latex_characters(
              job_meta.get("recipient_name", "Hiring Manager")
          ),
      )
      .replace(
          "__RECIPIENT_TITLE__",
          sanitize_latex_characters(job_meta.get("recipient_title", "")),
      )
      .replace(
          "__COMPANY_NAME__",
          sanitize_latex_characters(job_meta.get("company_name", "")),
      )
      .replace(
          "__COMPANY_ADDRESS__",
          sanitize_latex_characters(job_meta.get("company_address", "")),
      )
      .replace(
          "__JOB_TITLE__",
          sanitize_latex_characters(job_meta.get("job_title", "")),
      )
      .replace("__SALUTATION__", sanitize_latex_characters(salutation))
      .replace("__BODY_CONTENT__", final_latex_body)
  )

  # 4. Save and Compile
  tex_filepath = os.path.join(output_dir, "cover_letter.tex")
  ensure_parent_dir(tex_filepath)
  with open(tex_filepath, "w", encoding="utf-8") as f:
    f.write(latex_document)

  print(f"[✓] Saved LaTeX Cover Letter to: {tex_filepath}")

  if compile_pdf:
    try:
      cmd = [
          "pdflatex",
          f"-output-directory={output_dir}",
          "-interaction=nonstopmode",
          tex_filepath,
      ]
      subprocess.run(
          cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
      )
      pdf_filepath = os.path.join(output_dir, "cover_letter.pdf")
      print(f"[✓] Successfully compiled PDF to: {pdf_filepath}")
      return pdf_filepath
    except subprocess.CalledProcessError as e:
      print(
          "[!] pdflatex compilation error:"
          f" {e.stderr.decode('utf-8', errors='ignore')}"
      )
      return tex_filepath

  return tex_filepath

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

  # 3. Process CV sections and company entries
  tailored_tex = update_cv_sections(full_tex, job_description)

  # 4. Save reassembled LaTeX CV file
  cv_tex_path = os.path.join(OUTPUT_DIR, f"{OUTPUT_BASENAME}.tex")
  with open(cv_tex_path, "w", encoding="utf-8") as f:
    f.write(tailored_tex)
  print(f"[✓] Saved reassembled LaTeX CV to: {cv_tex_path}")

  # 5. Compile CV PDF (output/cv.pdf)
  compile_latex_to_pdf(cv_tex_path, OUTPUT_DIR)

  # 6. Generate and Compile Cover Letter PDF (output/cover_letter.pdf)
  candidate_data = extract_candidate_metadata_and_context(
        selected_cv_path, job_description
    )
  
  generate_nus_cover_letter(
        candidate_data=candidate_data, job_description=job_description
    )


if __name__ == "__main__":
  main()
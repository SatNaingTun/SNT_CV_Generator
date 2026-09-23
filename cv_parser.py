import datetime
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional
from config import CV_FOLDER, MODEL_NAME, OUTPUT_FOLDER, DB_NAME, DATA_FOLDER
from db_manager import SQLiteCRUD
from job_manager import load_job_history
from latex_reader import LaTeXReader
from latex_writer import LaTeXWriter
from llm_client import client
from tqdm import tqdm
from utils import extract_text_from_file

# Safe PyLaTeX import
try:
  import pylatex
  from pylatex.utils import escape_latex

  HAS_PYLATEX = True
except ImportError:
  HAS_PYLATEX = False


def filter_tex_over_pdf(files: List[str]) -> List[str]:
  """Deduplicates files:
  1. Strips ' copy' artifacts from filenames.
  2. If both a .tex and .pdf exist for the same name, keeps ONLY the .tex file.
  """
  stem_map = {}
  for filepath in files:
    base = os.path.basename(filepath)
    stem, ext = os.path.splitext(base)
    ext = ext.lower()

    clean_stem = re.sub(
        r"\s+copy(?:\s+\d+)?$", "", stem, flags=re.IGNORECASE
    ).strip()

    if clean_stem not in stem_map:
      stem_map[clean_stem] = {}
    stem_map[clean_stem][ext] = filepath

  deduped_files = []
  for stem, ext_dict in stem_map.items():
    if ".tex" in ext_dict:
      deduped_files.append(ext_dict[".tex"])
    elif ".pdf" in ext_dict:
      deduped_files.append(ext_dict[".pdf"])

  return sorted(deduped_files)


def _parse_tex_natively(filepath: str, raw_text: str) -> Optional[Dict[str, Any]]:
  """Deterministically parses a .tex CV file entirely using LaTeXReader methods."""
  try:
    reader = LaTeXReader(raw_text)
    
    education = reader.parse_education()
    experience = reader.parse_experience()
    projects = reader.parse_projects()
    skills = reader.parse_technical_skills()
    
    if not (education or experience or projects or skills):
      return None

    candidate_name = reader.parse_candidate_name()
    contact_info = reader.parse_contact_info()
    summaries = reader.parse_summary()

    tech_skills_dict = {}
    for skill_group in skills:
      if isinstance(skill_group, dict):
        category = skill_group.get("title", "Technical Skills")
        items = skill_group.get("bullet_points", [])
        tech_skills_dict[category] = items

    formatted_experience = []
    for exp in experience:
      if isinstance(exp, dict):
        formatted_experience.append({
            "job_title": exp.get("title", ""),
            "company": exp.get("metadata", ""),
            "from": exp.get("from", ""),
            "to": exp.get("to", ""),
            "bullet_points": exp.get("bullet_points", [])
        })

    formatted_projects = []
    for proj in projects:
      if isinstance(proj, dict):
        formatted_projects.append({
            "project_name": proj.get("title", ""),
            "dates": proj.get("metadata", ""),
            "tech_stack": [],
            "details": proj.get("bullet_points", [])
        })

    abs_path = os.path.abspath(filepath)
    filename = os.path.basename(filepath)

    return {
        "candidate_name": candidate_name,
        "target_role": "",
        "contact_info": contact_info,
        "summaries": summaries,
        "technical_skills": tech_skills_dict,
        "core_competencies": [],
        "work_experience": formatted_experience,
        "education": education,  # Already validated and formatted inside LaTeXReader
        "projects": formatted_projects,
        "certifications": reader.parse_certificates(),
        "languages": [],
        "file_path": abs_path,
        "source_file": filename,
        "latex_granular": {
            "education_structured": education,
            "experience_structured": experience,
            "projects_structured": projects,
            "skills_structured": skills,
            "sections": reader.sections
        }
    }
  except Exception:
    return None


def _parse_cv_with_llm(filepath: str, raw_text: str) -> Dict[str, Any]:
  """Parses CV files (such as PDFs) using the LLM parser."""
  abs_path = os.path.abspath(filepath)
  filename = os.path.basename(filepath)

  prompt = f"""Extract full detailed CV information into precise JSON from this CV file content ({filename}).
Preserve all rich details, full bullet points, exact dates, institutions, degrees, projects, and certifications.

=== CV FILE CONTENT ({filename}) ===
{raw_text[:8000]}

=== JSON OUTPUT SCHEMA ===
{{
  "candidate_name": "Full Candidate Name",
  "target_role": "Target Role or Job Title",
  "contact_info": "Email | Phone | LinkedIn | GitHub",
  "summaries": ["Professional summary text"],
  "technical_skills": {{
    "Category Name": ["Skill 1", "Skill 2"]
  }},
  "core_competencies": ["Competency 1", "Competency 2"],
  "work_experience": [
    {{
      "job_title": "Job Title",
      "company": "Company Name",
      "from": "Start Date",
      "to": "End Date",
      "bullet_points": ["Detailed bullet point 1"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree Title",
      "institution": "University Name",
      "from": "Start Date",
      "to": "End Date",
      "coursework": ["Course 1"],
      "thesis": "Thesis title"
    }}
  ],
  "projects": [
    {{
      "project_name": "Project Name",
      "dates": "Dates",
      "tech_stack": ["Tech 1"],
      "details": ["Detail 1"]
    }}
  ],
  "certifications": [
    {{
      "certificate_name": "Name of Certificate",
      "certificate_id": "ID if available",
      "from": "From date",
      "to": "To date",
      "url": "URL if available"
    }}
  ],
  "languages": ["Language 1"]
}}
"""

  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are an expert CV parser. Extract structured resume data accurately into JSON.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content_str = response.choices[0].message.content.strip()
    parsed = json.loads(content_str)
    
    if not isinstance(parsed, dict):
      return {}

    parsed["file_path"] = abs_path
    parsed["source_file"] = filename
    parsed["latex_granular"] = {}
    return parsed
  except Exception:
    return {}


def parse_cv_file(filepath: str) -> Dict[str, Any]:
  """Parses CV files using native LaTeX extraction or LLM fallback."""
  try:
    with open(filepath, "r", encoding="utf-8") as f:
      raw_text = f.read()
  except Exception:
    try:
      raw_text = extract_text_from_file(filepath)
    except Exception:
      return {}

  if not raw_text.strip():
    return {}

  if filepath.endswith(".tex"):
    native_result = _parse_tex_natively(filepath, raw_text)
    if native_result:
      return native_result

  try:
    return _parse_cv_with_llm(filepath, raw_text)
  except Exception:
    return {}


def select_optimal_cv_file(cv_folder: str) -> Optional[str]:
  """Selects the best matching CV template based on the cached job description."""
  raw_files = glob.glob(os.path.join(cv_folder, "*.tex")) + glob.glob(
      os.path.join(cv_folder, "*.pdf")
  )
  files = filter_tex_over_pdf(raw_files)
  
  if not files:
    return None

  if len(files) == 1:
    return files[0]

  job_data = load_job_history()
  job_description = job_data.get("raw_text", "") or json.dumps(job_data, indent=2)

  file_options = {os.path.basename(f): f for f in files}

  system_prompt = (
      "You are an expert career advisor. Select the single most relevant CV template "
      "file from the available options that best matches the target job description. "
      "Output ONLY the exact filename in JSON format like: {\"selected_file\": \"filename.tex\"}"
  )

  user_prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:3000]}

=== AVAILABLE CV TEMPLATES ===
{list(file_options.keys())}

INSTRUCTIONS:
Choose the best matching template file name.
"""

  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content.strip())
    selected_name = result.get("selected_file")
    if selected_name in file_options:
      return file_options[selected_name]
  except Exception:
    pass

  return files[0]


def build_sqlite_master_profile(
    cv_folder: str = CV_FOLDER,
    output_folder: str = OUTPUT_FOLDER,
    force_rebuild: bool = False,
) -> str:
  """Scans all CV files, parses them, and populates SQLite DB."""
  db_path = os.path.join(DATA_FOLDER, DB_NAME)
  db = SQLiteCRUD(db_path)

  raw_files = glob.glob(os.path.join(cv_folder, "*.tex")) + glob.glob(
      os.path.join(cv_folder, "*.pdf")
  )
  files = filter_tex_over_pdf(raw_files)

  if not files:
    db.close()
    return db_path

  if force_rebuild:
    db.clear_all()

  pbar = tqdm(files, desc="Processing CV files", unit="file")
  
  for filepath in pbar:
    try:
      rel_path = os.path.basename(filepath)
      abs_path = os.path.abspath(filepath)
      
      pbar.set_postfix(file=rel_path)

      mtime = os.path.getmtime(filepath)
      formatted_date = datetime.datetime.fromtimestamp(mtime).strftime(
          "%Y-%m-%d %H:%M:%S"
      )

      stored_mtime = db.get_file_mtime(rel_path)
      if stored_mtime is not None and not force_rebuild and stored_mtime == mtime:
        continue

      parsed_data = parse_cv_file(abs_path)
      if not parsed_data:
        continue

      db.upsert_scanned_file(rel_path, abs_path, mtime, formatted_date)

      sections = ["summary", "education", "experience", "project", "certificate", "language", "skills"]
      for section in tqdm(sections, desc="   -> Inserting sections", leave=False):
        if section == "summary":
          db.store_summary_section(parsed_data, rel_path)
        elif section == "education":
          db.store_education_section(parsed_data)
        elif section == "experience":
          db.store_experience_section(parsed_data)
        elif section == "project":
          db.store_project_section(parsed_data)
        elif section == "certificate":
          db.store_certificate_section(parsed_data)
        elif section == "language":
          db.store_language_section(parsed_data)
        elif section == "skills":
          db.store_skills_section(parsed_data, rel_path)

    except Exception as e:
      print(f"\n[!] Error processing file {filepath}: {e}")
      continue

  db.close()
  return db_path


def main():
  """CLI entry point to scan CV folder and update SQLite database."""
  force_rebuild = "--force" in sys.argv or "-f" in sys.argv

  custom_folder = None
  for arg in sys.argv[1:]:
    if not arg.startswith("-"):
      custom_folder = arg
      break

  target_cv_folder = custom_folder or CV_FOLDER
  target_output_folder = OUTPUT_FOLDER

  db_path = build_sqlite_master_profile(
      cv_folder=target_cv_folder,
      output_folder=target_output_folder,
      force_rebuild=force_rebuild,
  )

  abs_db_path = os.path.abspath(db_path)
  print(abs_db_path)


if __name__ == "__main__":
  main()
import json
import os
import re
from config import CV_FOLDER, MODEL_NAME, OUTPUT_BASENAME, OUTPUT_FOLDER, DATA_FOLDER, DB_NAME, RESUME_FORMAT
from job_manager import get_or_cache_job_description
from latex_reader import LaTeXReader
from latex_writer import LaTeXWriter
from llm_client import client
from cv_parser import select_optimal_cv_file, build_sqlite_master_profile
from db_manager import SQLiteCRUD
from utils import (
    compile_latex_to_pdf,
    format_job_summary,
    prompt_for_job_description,
)


def split_into_sentences(text: str) -> list:
  """Splits a paragraph of text strictly into individual sentences."""
  if not text:
    return []
  raw_sentences = re.split(r'(?<=[.!?])\s+', text.strip())
  return [s.strip() for s in raw_sentences if s.strip()]


def clean_llm_response(text: str) -> str:
  """Strips conversational boilerplate prefixes from LLM outputs."""
  if not text:
    return ""
  cleaned = re.sub(r"^(Here(?:'s| is) (?:a|the|some)?\s*(?:tailored)?\s*(?:professional)?\s*(?:summary|text|content|body content).*?[:\n])", "", text, flags=re.IGNORECASE)
  return cleaned.strip()

def query_and_tailor_skills(job_summary_str: str, base_skills: dict) -> dict:
  print("[+] Tailoring section: 'Technical Skills'...")
  
  # Filter out any non-skill keys just in case
  ignored_categories = {"education", "certifications", "languages", "nationalities"}
  filtered_base_skills = {
      k: v for k, v in base_skills.items() 
      if k.lower() not in ignored_categories
  }

  system_prompt = (
      "You are an expert technical resume editor. Your job is to select and re-order the candidate's actual technical skills "
      "so they match the priorities of the target job description. "
      "CRITICAL: Do NOT invent, fabricate, or add skills the candidate does not already possess. Only use the candidate's existing skills provided below."
  )
  user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== CANDIDATE'S EXISTING TECHNICAL SKILLS ===
{json.dumps(filtered_base_skills, indent=2)}

INSTRUCTIONS:
1. Re-organize, prioritize, and filter the candidate's technical skill categories to highlight what matters most for the target job.
2. Keep ONLY the skills the candidate actually has (from the candidate's existing skills list above). Do not add new technologies.
3. Return a valid JSON object where keys are technical categories (e.g., Programming Languages, Cloud & DevOps, Databases, Tools & Frameworks) and values are arrays of skill strings.
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content.strip())
    # Fallback to filtered base skills if result is empty
    if not result:
      return filtered_base_skills
    return {k: v for k, v in result.items() if k.lower() not in ignored_categories and v}
  except Exception as e:
    print(f"[!] Skills section tailoring failed: {e}. Using base skills.")
    return filtered_base_skills


import re

def clean_llm_response(text: str) -> str:
  """Strips conversational boilerplate prefixes from LLM outputs."""
  if not text:
    return ""
  # Remove common conversational intros
  cleaned = re.sub(r"^(Here(?:'s| is) (?:a|the|some)?\s*(?:tailored)?\s*(?:professional)?\s*(?:summary|text|content|body content).*?[:\n])", "", text, flags=re.IGNORECASE)
  return cleaned.strip()

def query_section_llm(
    section_name: str, section_content: str, job_summary_str: str
) -> str:
  print(f"[+] Tailoring section: '{section_name}'...")
  system_prompt = (
      "You are a strict text formatter and CV editor. "
      "CRITICAL: Output ONLY the raw tailored text. NEVER include conversational filler, chatty introductions, or phrases like 'Here is your summary'. Return zero introductory text."
  )
  user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION CONTENT ===
{section_content}

INSTRUCTIONS:
1. Tailor the content professionally for the target role while staying strictly truthful to the original content.
2. Output ONLY the raw content body without any introduction or conversational wrapper.
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
    raw_output = response.choices[0].message.content.strip()
    return clean_llm_response(raw_output)
  except Exception as e:
    print(f"[!] Section API request failed for '{section_name}': {e}")
    return section_content


def generate_tailored_cv(
    template_path: str, job_data: dict, output_path: str
) -> str:
  print(f"\n[+] Analyzing selected template: {os.path.basename(template_path)}")
  print(f"[+] Active Format Mode: {RESUME_FORMAT.upper()}")

  with open(template_path, "r", encoding="utf-8", errors="ignore") as f:
    raw_tex = f.read()

  reader = LaTeXReader(raw_tex)

  candidate_name = reader.parse_candidate_name() or "Sat Naing Tun"
  contact_info = reader.parse_contact_info() or {}

  base_summaries = reader.parse_summary()
  raw_summary = base_summaries[0] if base_summaries else ""

  base_experience = reader.parse_experience()
  base_projects = reader.parse_projects()
  base_education = reader.parse_education()
  base_certifications = reader.parse_certificates()
  base_languages = reader.parse_languages()
  base_core_competencies = reader.parse_core_competencies()
  
  parsed_skills = reader.parse_technical_skills()
  base_skills_dict = {}
  for s_group in parsed_skills:
    if isinstance(s_group, dict):
      base_skills_dict[s_group.get("title", "Technical Skills")] = s_group.get("bullet_points", [])

  db_path = os.path.join(DATA_FOLDER, DB_NAME)
  build_sqlite_master_profile(cv_folder=CV_FOLDER)
  db = SQLiteCRUD(db_path)
  db.close()

  job_summary_str = format_job_summary(job_data)

  # Tailor Summary as a clean single paragraph block
  tailored_summary_text = query_section_llm("Professional Summary", raw_summary, job_summary_str)
  tailored_summary_paragraph = " ".join([line.strip() for line in tailored_summary_text.split("\n") if line.strip()])

  # Tailor Experience sentences into individual itemized bullets
  tailored_experience = []
  for exp in base_experience:
    title = exp.get("title", "")
    company = exp.get("company", "")
    from_d = exp.get("from", "")
    to_d = exp.get("to", "")
    bullets = exp.get("bullet_points", [])
    
    bullet_text_block = "\n".join([f"- {b}" for b in bullets])
    tailored_block = query_section_llm(f"Experience at {company}", bullet_text_block, job_summary_str)
    
    raw_lines = [line.lstrip("- ").strip() for line in tailored_block.split("\n") if line.strip()]
    tailored_bullets = []
    for line in raw_lines:
      tailored_bullets.extend(split_into_sentences(line))
    
    tailored_experience.append({
        "job_title": title,
        "company": company,
        "from": from_d,
        "to": to_d,
        "bullet_points": tailored_bullets if tailored_bullets else bullets
    })

  projects_list = []
  for proj in base_projects:
    projects_list.append({
        "project_name": proj.get("project_name", ""),
        "tech_stack": proj.get("tech_stack", []),
        "details": proj.get("details", [])
    })

  education_list = []
  for edu in base_education:
    education_list.append({
        "degree": edu.get("degree", ""),
        "institution": edu.get("institution", ""),
        "from": edu.get("from", ""),
        "to": edu.get("to", ""),
        "coursework": edu.get("coursework", []),  # <--- Use parsed coursework directly without generic defaults
        "thesis": edu.get("thesis", "")
    })

  cert_list = []
  for cert in base_certifications:
    cert_list.append({
        "certificate_name": cert.get("certificate_name", ""),
        "issuing_organization": cert.get("issuing_organization", ""),
        "from": cert.get("from", ""),
        "to": cert.get("to", ""),
        "url": cert.get("url", "")
    })

  tailored_skills_dict = query_and_tailor_skills(job_summary_str, base_skills_dict)
  languages_list = base_languages
  core_competencies_list = base_core_competencies

  doc_parts = [
      LaTeXWriter.initialize_document_from_template(raw_tex, RESUME_FORMAT),
      LaTeXWriter.extract_header_block(candidate_name, contact_info)
  ]

  # Render summary as a smooth paragraph block
  if tailored_summary_paragraph:
    doc_parts.append(LaTeXWriter.write_summary_section(tailored_summary_paragraph))

  if tailored_skills_dict:
    doc_parts.append(LaTeXWriter.write_skills_section(tailored_skills_dict))

  if core_competencies_list:
    doc_parts.append(LaTeXWriter.write_core_competencies_section(core_competencies_list))

  if education_list:
    doc_parts.append(LaTeXWriter.write_education_section(education_list))

  if tailored_experience:
    doc_parts.append(LaTeXWriter.write_experience_section(tailored_experience))

  if projects_list:
    doc_parts.append(LaTeXWriter.write_projects_section(projects_list))

  if cert_list:
    doc_parts.append(LaTeXWriter.write_certifications_section(cert_list))

  if languages_list:
    doc_parts.append(LaTeXWriter.write_languages_section(languages_list))

  doc_parts.append("\\end{document}")
  final_latex_content = "\n".join(doc_parts)

  output_dir = os.path.dirname(output_path)
  os.makedirs(output_dir, exist_ok=True)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(final_latex_content)

  print(f"[✓] Tailored LaTeX saved to: {output_path}")
  compile_latex_to_pdf(output_path, output_dir)

  return output_path


if __name__ == "__main__":
  raw_input = prompt_for_job_description()
  job_data = get_or_cache_job_description(raw_input)

  selected_template = select_optimal_cv_file(CV_FOLDER)

  base_filename = (
      os.path.splitext(OUTPUT_BASENAME)[0]
      if OUTPUT_BASENAME.endswith(".tex")
      else OUTPUT_BASENAME
  )
  output_tex_file = os.path.join(OUTPUT_FOLDER, f"{base_filename}.tex")

  generate_tailored_cv(selected_template, job_data, output_tex_file)
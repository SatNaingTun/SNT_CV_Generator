import json
import os
import re
from config import CV_FOLDER, MODEL_NAME, OUTPUT_BASENAME, OUTPUT_FOLDER, DATA_FOLDER, DB_NAME, RESUME_FORMAT
from job_manager import get_or_cache_job_description
from latex_reader import LaTeXReader
from latex_cv_writer import LaTeXCVWriter  # Updated import
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
3. Return a valid JSON object where keys are technical categories and values are arrays of skill strings.
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content.strip())
    if not result:
      return filtered_base_skills
    return {k: v for k, v in result.items() if k.lower() not in ignored_categories and v}
  except Exception as e:
    print(f"[!] Skills section tailoring failed: {e}. Using base skills.")
    return filtered_base_skills


def query_and_tailor_projects(job_summary_str: str, base_projects: list) -> list:
  print("[+] Tailoring and filtering section: 'Projects'...")
  if not base_projects:
    return []

  system_prompt = (
      "You are an expert technical resume editor. Your job is to filter the candidate's projects "
      "so that ONLY projects directly related to the target job description are included, and duplicates, "
      "obsolete, or irrelevant projects are removed. "
      "CRITICAL: Do NOT invent, fabricate, or add projects the candidate did not execute. Use only the candidate's existing projects."
  )
  user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== CANDIDATE'S PROJECTS ===
{json.dumps(base_projects, indent=2)}

INSTRUCTIONS:
1. Evaluate each project against the target job specifications. Filter out any projects that lack relevance, overlap redundantly (duplicates), or do not match the required domain/tech stack.
2. Retain only the most impactful, targeted projects that strengthen the candidate's fit for this specific role.
3. Return a valid JSON object with a single key "projects" containing an array of project objects. Each project must have "project_name" (string), "tech_stack" (array of strings), and "details" (array of strings).
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content.strip())
    selected_projects = result.get("projects", [])
    
    if not selected_projects:
      return base_projects
    
    # Ensure details are properly formatted as a list of bullet strings
    cleaned_projects = []
    for proj in selected_projects:
      details = proj.get("details", [])
      if isinstance(details, str):
        details = [details]
      cleaned_projects.append({
          "project_name": proj.get("project_name", ""),
          "tech_stack": proj.get("tech_stack", []),
          "details": details
      })
    return cleaned_projects
  except Exception as e:
    print(f"[!] Projects section tailoring failed: {e}. Using base projects.")
    return base_projects


def query_section_llm(
    section_name: str, section_content: str, job_summary_str: str
) -> str:
  print(f"[+] Tailoring section: '{section_name}'...")

  if "summary" in section_name.lower():
    system_prompt = (
        "You are an expert executive resume writer and ATS optimization specialist. "
        "Your task is to craft a compelling professional summary that explicitly connects the candidate's actual background to why they are a strong fit for the target role. "
        "CRITICAL: Output ONLY the raw tailored text. NEVER include conversational filler or introductions."
    )
    user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION CONTENT ===
{section_content}

INSTRUCTIONS:
1. Rewrite this professional summary to highlight the core strengths, technical skills, and background that directly make the candidate an ideal fit for the target job specifications.
2. Keep the content strictly rooted in the candidate's actual experience (do not invent jobs or degrees).
3. Output ONLY the raw content body without any introduction or wrapper.
"""
  elif "experience" in section_name.lower():
    system_prompt = (
        "You are a strict and honest technical resume editor. Your job is to refine experience bullet points "
        "for clarity and professional tone WITHOUT fabricating new responsibilities, fake metrics, or unowned tools. "
        "CRITICAL: Output ONLY the raw tailored text. NEVER include conversational filler."
    )
    user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION CONTENT ===
{section_content}

INSTRUCTIONS:
1. Refine these existing experience bullet points to improve clarity, flow, and professional impact.
2. DO NOT invent or fabricate fake metrics (e.g., "$500k revenue uplift", "99.99% uptime", custom customer churn percentages) unless they are explicitly present in the original content.
3. Keep the technical stack and duties completely truthful to the original text. Only subtly emphasize elements that relate to the target job.
4. Output ONLY the raw bullet points without any introduction.
"""
  else:
    system_prompt = (
        "You are an expert professional resume editor. "
        "CRITICAL: Output ONLY the raw tailored text. NEVER include conversational filler or introductions."
    )
    user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION CONTENT ===
{section_content}

INSTRUCTIONS:
1. Tailor this section to highlight skills and focus areas matching the target job specifications.
2. Keep all facts strictly truthful to the original content.
3. Output ONLY the raw content body without any introduction.
"""

  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # Lowered temperature slightly to keep experience grounded and realistic
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
  print(f"\n[+] Fetching profile data from SQLite database...")
  print(f"[+] Active Format Mode: {RESUME_FORMAT.upper()}")

  db_path = os.path.join(DATA_FOLDER, DB_NAME)
  build_sqlite_master_profile(cv_folder=CV_FOLDER)
  db = SQLiteCRUD(db_path)

  contact_data = db.get_contact_info()
  candidate_name = contact_data.get("candidate_name", "Sat Naing Tun")
  contact_info = {
      "email": contact_data.get("email", ""),
      "phone": contact_data.get("phone", ""),
      "linkedin": contact_data.get("linkedin", ""),
      "github": contact_data.get("github", "")
  }

  raw_summary = db.get_summary()
  base_education = db.get_education()
  base_experience = db.get_experience()
  base_projects = db.get_projects()
  base_certifications = db.get_certifications()
  base_languages = db.get_languages()
  base_core_competencies = db.get_core_competencies()
  base_skills_dict = db.get_technical_skills()
  
  db.close()

  with open(template_path, "r", encoding="utf-8", errors="ignore") as f:
    raw_tex = f.read()

  job_summary_str = format_job_summary(job_data)

  tailored_summary_text = query_section_llm("Professional Summary", raw_summary, job_summary_str)
  tailored_summary_paragraph = " ".join([line.strip() for line in tailored_summary_text.split("\n") if line.strip()])

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

  projects_list = query_and_tailor_projects(job_summary_str, base_projects)

  education_list = []
  for edu in base_education:
    education_list.append({
        "degree": edu.get("degree", ""),
        "institution": edu.get("institution", ""),
        "from": edu.get("from", ""),
        "to": edu.get("to", ""),
        "coursework": edu.get("coursework", []),
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
      LaTeXCVWriter.initialize_document_from_template(raw_tex, RESUME_FORMAT),
      LaTeXCVWriter.extract_header_block(candidate_name, contact_info)
  ]

  if tailored_summary_paragraph:
    doc_parts.append(LaTeXCVWriter.write_summary_section(tailored_summary_paragraph))

  if tailored_skills_dict:
    doc_parts.append(LaTeXCVWriter.write_skills_section(tailored_skills_dict))

  if core_competencies_list:
    doc_parts.append(LaTeXCVWriter.write_core_competencies_section(core_competencies_list))

  if education_list:
    doc_parts.append(LaTeXCVWriter.write_education_section(education_list))

  if tailored_experience:
    doc_parts.append(LaTeXCVWriter.write_experience_section(tailored_experience))

  if projects_list:
    doc_parts.append(LaTeXCVWriter.write_projects_section(projects_list))

  if cert_list:
    doc_parts.append(LaTeXCVWriter.write_certifications_section(cert_list))

  if languages_list:
    doc_parts.append(LaTeXCVWriter.write_languages_section(languages_list))

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
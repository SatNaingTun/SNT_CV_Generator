import json
import os
from config import CV_FOLDER, MODEL_NAME, OUTPUT_BASENAME, OUTPUT_FOLDER
from job_manager import get_or_cache_job_description
from latex_reader import LaTeXReader
from latex_utils import (
    convert_tabularx_to_itemize_skills,
    remove_manual_pagebreaks,
    replace_section_in_raw_tex,
    replace_skills_section_in_raw_tex,
    strip_section_headers,
)
from latex_writer import LaTeXWriter
from llm_client import client
from profile_manager import select_optimal_cv_file
from utils import (
    compile_latex_to_pdf,
    format_job_summary,
    prompt_for_job_description,
)


def query_and_update_skills_section(
    raw_tex: str, job_summary_str: str, existing_skills: dict
) -> str:
  """Extracts technical skills, tailors them via LLM using structured job specs, and replaces section."""
  print("[+] Tailoring section: 'Technical Skills'...")

  system_prompt = (
      "You are an expert technical resume editor. Output ONLY a valid JSON object "
      "mapping technical skill categories to comma-separated skill items. "
      "Do NOT drop essential core skills from the existing skills list."
  )

  user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== EXISTING CANDIDATE SKILLS ===
{json.dumps(existing_skills, indent=2) if existing_skills else "Extract and optimize based on target role."}

INSTRUCTIONS:
1. Re-organize and tailor technical skills to align with target job specifications and required skills.
2. Output STRICT JSON format mapping category names to comma-separated skill strings.
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
    tailored_skills_dict = json.loads(
        response.choices[0].message.content.strip()
    )
    new_skills_latex = LaTeXWriter.write_skills_as_list(tailored_skills_dict)
    return replace_skills_section_in_raw_tex(raw_tex, new_skills_latex)

  except Exception as e:
    print(
        f"[!] Skills section tailoring failed: {e}. Falling back to clean"
        " itemize conversion of original skills."
    )
    return convert_tabularx_to_itemize_skills(raw_tex)


def query_section_llm(
    section_name: str, section_content: str, job_summary_str: str
) -> str:
  """Tailors standard resume prose sections (Summary, Experience, Projects) using structured job specs."""
  print(f"[+] Tailoring section: '{section_name}'...")

  system_prompt = (
      "You are a professional CV editor. Output ONLY the tailored LaTeX body content. "
      "Do NOT include outer \\section{} headers or commentary."
  )

  user_prompt = f"""=== TARGET JOB SPECIFICATIONS ===
{job_summary_str}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION CONTENT ===
{section_content}

INSTRUCTIONS:
1. Tailor bullet points and summary text to match key specifications, required skills, certifications, and language requirements.
2. Preserve valid LaTeX formatting and itemize structures.
3. Output ONLY the body snippet without wrapping section commands.
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
    clean_body = strip_section_headers(raw_output)
    return LaTeXWriter.write_sentence(clean_body)

  except Exception as e:
    print(f"[!] Section API request failed for '{section_name}': {e}")
    return section_content


def generate_tailored_cv(
    template_path: str, job_data: dict, output_path: str
) -> str:
  """Main pipeline: Reads template, strips manual pagebreaks, tailors sections using structured job specifications,

  saves output .tex, and compiles to PDF via utils.
  """
  print(
      f"\n[+] Processing selected template: {os.path.basename(template_path)}"
  )

  with open(template_path, "r", encoding="utf-8", errors="ignore") as f:
    raw_tex = f.read()

  # 1. Format structured job requirements
  job_summary_str = format_job_summary(job_data)

  # 2. Remove hardcoded \newpage commands
  raw_tex = remove_manual_pagebreaks(raw_tex)

  # 3. Convert tabularx tables to itemize blocks
  raw_tex = convert_tabularx_to_itemize_skills(raw_tex)

  # 4. Tailor Technical Skills section
  existing_skills = LaTeXReader.extract_skills_dict(raw_tex)
  raw_tex = query_and_update_skills_section(
      raw_tex, job_summary_str, existing_skills
  )

  # 5. Tailor Professional Summary section
  reader = LaTeXReader(raw_tex)
  summary_content = (
      reader.get_section("SUMMARY")
      or reader.get_section("PROFESSIONAL SUMMARY")
      or reader.get_section("OBJECTIVE")
  )

  if summary_content:
    sec_title = (
        "PROFESSIONAL SUMMARY"
        if "PROFESSIONAL SUMMARY" in raw_tex
        else ("SUMMARY" if "SUMMARY" in raw_tex else "OBJECTIVE")
    )
    tailored_summary = query_section_llm(
        sec_title, summary_content, job_summary_str
    )
    raw_tex = replace_section_in_raw_tex(raw_tex, sec_title, tailored_summary)

  # 6. Save tailored LaTeX file
  output_dir = os.path.dirname(output_path)
  os.makedirs(output_dir, exist_ok=True)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(raw_tex)

  print(f"[✓] Tailored LaTeX saved to: {output_path}")

  # 7. Compile to PDF using utils function
  compile_latex_to_pdf(output_path, output_dir)

  return output_path


if __name__ == "__main__":
  raw_input = prompt_for_job_description()
  job_data = get_or_cache_job_description(raw_input)

  selected_template = select_optimal_cv_file(
      CV_FOLDER, job_data.get("raw_text", raw_input)
  )

  base_filename = (
      os.path.splitext(OUTPUT_BASENAME)[0]
      if OUTPUT_BASENAME.endswith(".tex")
      else OUTPUT_BASENAME
  )
  output_tex_file = os.path.join(OUTPUT_FOLDER, f"{base_filename}.tex")

  generate_tailored_cv(selected_template, job_data, output_tex_file)
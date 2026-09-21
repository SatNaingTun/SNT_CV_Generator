import json
import os
import re
import subprocess
from config import CV_FOLDER, MODEL_NAME, OUTPUT_BASENAME, OUTPUT_DIR as OUTPUT_FOLDER
from latex_reader import LaTeXReader
from latex_utils import (
    convert_tabularx_to_itemize_skills,
    replace_skills_section_in_raw_tex,
    strip_section_headers,
)
from latex_writer import LaTeXWriter
from llm_client import client
from profile_manager import select_optimal_cv_file


def replace_section_in_raw_tex(
    raw_tex: str, section_name: str, new_content: str
) -> str:
  """Replaces a specific section's body using lambda string insertion to avoid backslash escape crashes."""
  pattern = re.compile(
      r"(\\section\*?\{"
      + re.escape(section_name)
      + r"\}\s*\n)(.*?)(?=\n\\section|\n\\end\{document\}|\Z)",
      re.DOTALL | re.IGNORECASE,
  )

  if pattern.search(raw_tex):
    return pattern.sub(lambda m: m.group(1) + new_content + "\n", raw_tex)

  fuzzy_pattern = re.compile(
      r"(\\section\*?\{[^}]*"
      + re.escape(section_name)
      + r"[^}]*\}\s*\n)(.*?)(?=\n\\section|\n\\end\{document\}|\Z)",
      re.DOTALL | re.IGNORECASE,
  )

  if fuzzy_pattern.search(raw_tex):
    return fuzzy_pattern.sub(lambda m: m.group(1) + new_content + "\n", raw_tex)

  return raw_tex


def query_and_update_skills_section(raw_tex: str, job_description: str) -> str:
  """Extracts technical skills, tailors them via LLM, and replaces section with LaTeX itemize block."""
  print("[+] Tailoring section: 'Technical Skills'...")

  existing_skills = LaTeXReader.extract_skills_dict(raw_tex)

  system_prompt = (
      "You are an expert technical resume editor. Output ONLY a valid JSON object "
      "mapping technical skill categories to comma-separated skill items. "
      "Do NOT drop essential core skills from the existing skills list."
  )

  user_prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:1500]}

=== EXISTING CANDIDATE SKILLS ===
{json.dumps(existing_skills, indent=2) if existing_skills else "Extract and optimize based on target role."}

INSTRUCTIONS:
1. Re-organize and tailor technical skills to align with target job requirements.
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
    section_name: str, section_content: str, job_description: str
) -> str:
  """Tailors standard resume prose sections (Summary, Experience, Projects) using LLM."""
  print(f"[+] Tailoring section: '{section_name}'...")

  system_prompt = (
      "You are a professional CV editor. Output ONLY the tailored LaTeX body content. "
      "Do NOT include outer \\section{} headers or commentary."
  )

  user_prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:1500]}

=== SECTION NAME ===
{section_name}

=== ORIGINAL SECTION CONTENT ===
{section_content}

INSTRUCTIONS:
1. Tailor bullet points and summary text to match key requirements from the job description.
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


def compile_latex(tex_filepath: str) -> bool:
  """Compiles the tailored .tex file into a PDF using pdflatex."""
  output_dir = os.path.dirname(tex_filepath)
  try:
    cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        tex_filepath,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    pdf_path = os.path.splitext(tex_filepath)[0] + ".pdf"
    print(f"[✓] Successfully compiled PDF: {pdf_path}")
    return True
  except (subprocess.CalledProcessError, FileNotFoundError) as e:
    print(f"[!] pdflatex compilation failed or pdflatex is not installed: {e}")
    return False


def generate_tailored_cv(
    template_path: str, job_description: str, output_path: str
) -> str:
  """Main pipeline: Reads template, converts tabularx skills to itemize,

  tailors sections via LLM, saves output .tex, and compiles to PDF.
  """
  print(
      f"\n[+] Processing selected template: {os.path.basename(template_path)}"
  )

  with open(template_path, "r", encoding="utf-8", errors="ignore") as f:
    raw_tex = f.read()

  # 1. Convert tabularx tables to itemize blocks
  raw_tex = convert_tabularx_to_itemize_skills(raw_tex)

  # 2. Tailor Technical Skills section
  raw_tex = query_and_update_skills_section(raw_tex, job_description)

  # 3. Tailor Professional Summary section
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
        sec_title, summary_content, job_description
    )
    raw_tex = replace_section_in_raw_tex(raw_tex, sec_title, tailored_summary)

  # 4. Save tailored LaTeX file using dynamic OUTPUT_BASENAME
  os.makedirs(os.path.dirname(output_path), exist_ok=True)
  with open(output_path, "w", encoding="utf-8") as f:
    f.write(raw_tex)

  print(f"[✓] Tailored LaTeX saved to: {output_path}")

  # 5. Compile to PDF
  compile_latex(output_path)

  return output_path


if __name__ == "__main__":
  target_job_description = """
    We are looking for an IT Systems Administrator / Software Engineer to support, maintain, and 
    enhance core IT infrastructure, SQL databases, and C# internal reporting software. 
    Experience with Linux servers, AWS, network troubleshooting, and Python automation is required.
    """

  # Select template
  selected_template = select_optimal_cv_file(
      CV_FOLDER, target_job_description
  )

  # Determine output .tex path based on OUTPUT_BASENAME config
  base_filename = (
      os.path.splitext(OUTPUT_BASENAME)[0]
      if OUTPUT_BASENAME.endswith(".tex")
      else OUTPUT_BASENAME
  )
  output_tex_file = os.path.join(OUTPUT_FOLDER, f"{base_filename}.tex")

  # Generate CV
  generate_tailored_cv(
      selected_template, target_job_description, output_tex_file
  )
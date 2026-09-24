import re
from latex_reader import LaTeXReader
from latex_cv_writer import LaTeXCVWriter


def sanitize_latex_characters(text: str, is_list: bool = True) -> str:
  """Delegates character escaping and syntax wrapping to LaTeXCVWriter."""
  if is_list:
    return LaTeXCVWriter.write_list(text)
  return LaTeXCVWriter.write_sentence(text)

def convert_tabularx_to_itemize_skills(raw_tex: str) -> str:
  """Detects any tabularx skills table in raw_tex, converts it to itemize format,

  and replaces the block in the document string.
  """
  reader = LaTeXReader(raw_tex)
  skills_dict = reader.extract_skills_dict(raw_tex)

  if not skills_dict:
    return raw_tex

  new_itemize_skills = LaTeXCVWriter.write_skills_as_list(skills_dict)
  return replace_skills_section_in_raw_tex(raw_tex, new_itemize_skills)


def replace_section_in_raw_tex(
    raw_tex: str, section_name: str, new_content: str
) -> str:
  """Single unified section replacement function for both standard and starred LaTeX sections."""
  pattern = re.compile(
      r"(\\section\*?\{"
      + re.escape(section_name)
      + r"\}\s*\n)(.*?)(?=\n\\section\*?|\n\\end\{document\}|\Z)",
      re.DOTALL | re.IGNORECASE,
  )

  if pattern.search(raw_tex):
    return pattern.sub(lambda m: m.group(1) + new_content + "\n", raw_tex)

  fuzzy_pattern = re.compile(
      r"(\\section\*?\{[^}]*"
      + re.escape(section_name)
      + r"[^}]*\}\s*\n)(.*?)(?=\n\\section\*?|\n\\end\{document\}|\Z)",
      re.DOTALL | re.IGNORECASE,
  )

  if fuzzy_pattern.search(raw_tex):
    return fuzzy_pattern.sub(lambda m: m.group(1) + new_content + "\n", raw_tex)

  return raw_tex


def convert_tabularx_to_itemize_skills(raw_tex: str) -> str:
  """Detects any tabularx skills table in raw_tex, converts it to itemize format,

  and replaces the block in the document string.
  """
  reader = LaTeXReader(raw_tex)
  skills_dict = reader.extract_skills_dict(raw_tex)

  if not skills_dict:
    return raw_tex

  new_itemize_skills = LaTeXCVWriter.write_skills_as_list(skills_dict)
  return replace_skills_section_in_raw_tex(raw_tex, new_itemize_skills)


def replace_skills_section_in_raw_tex(
    raw_tex: str, new_skills_latex: str
) -> str:
  """Replaces the Technical Skills section body using replace_section_in_raw_tex."""
  return replace_section_in_raw_tex(
      raw_tex, "Technical Skills", new_skills_latex
  )


def strip_section_headers(content: str) -> str:
  """Removes redundant \\section*{...} commands from LLM response text."""
  if not content:
    return ""
  return re.sub(r"^\s*\\section\*?\{[^}]+\}\s*", "", content).strip()


def remove_manual_pagebreaks(raw_tex: str) -> str:
  """Removes hardcoded \\newpage commands that cause layout clipping when sections expand."""
  return re.sub(r"\\newpage\b", "", raw_tex)


def strip_section_headers(content: str) -> str:
  """Removes redundant \\section*{...} commands from LLM response text."""
  if not content:
    return ""
  return re.sub(r"^\s*\\section\*?\{[^}]+\}\s*", "", content).strip()
import re
from latex_reader import LaTeXReader
from latex_writer import LaTeXWriter


def convert_tabularx_to_itemize_skills(raw_tex: str) -> str:
  """Detects any tabularx skills table in raw_tex, converts it to itemize format,

  and replaces the block in the document string.
  """
  reader = LaTeXReader(raw_tex)
  skills_dict = reader.extract_skills_dict(raw_tex)

  if not skills_dict:
    return raw_tex

  new_itemize_skills = LaTeXWriter.write_skills_as_list(skills_dict)
  return replace_skills_section_in_raw_tex(raw_tex, new_itemize_skills)


def replace_skills_section_in_raw_tex(
    raw_tex: str, new_skills_latex: str
) -> str:
  """Replaces the Technical Skills section body using a lambda replacement string

  to prevent re.sub backslash escape errors (e.g. \i in \item or \itemize).
  """
  pattern = re.compile(
      r"(\\section\*?\{[^}]*(?:Technical Skills|Skills)[^}]*\}\s*\n)"
      r"(?:\\begin\{tabularx\}.*?\\end\{tabularx\}|\\begin\{itemize\}.*?\\end\{itemize\}|.*?)"
      r"(?=\n\n\\|\n\\section|\n\\end\{document\}|\Z)",
      re.DOTALL | re.IGNORECASE,
  )

  if pattern.search(raw_tex):
    # Using lambda m: m.group(1) + ... bypasses backslash regex parsing
    return pattern.sub(lambda m: m.group(1) + new_skills_latex + "\n", raw_tex)

  return raw_tex


def strip_section_headers(content: str) -> str:
  """Removes redundant \\section*{...} commands from LLM response text."""
  if not content:
    return ""
  return re.sub(r"^\s*\\section\*?\{[^}]+\}\s*", "", content).strip()
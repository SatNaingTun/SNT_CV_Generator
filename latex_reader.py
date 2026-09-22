import os
import re


class LaTeXReader:
  """Reads LaTeX documents and extracts structured content directly using Regex."""

  def __init__(self, content_or_file: str):
    if os.path.exists(content_or_file):
      try:
        with open(
            content_or_file, "r", encoding="utf-8", errors="ignore"
        ) as f:
          self.raw_text = f.read()
      except Exception:
        self.raw_text = ""
    else:
      self.raw_text = content_or_file

  def get_section(self, section_name: str) -> str:
        """Extracts section body text by section header title."""
        if not self.raw_text:
            return ""

        pattern = re.compile(
            r"\\section\*?\{[^}]*"
            + re.escape(section_name)
            + r"[^}]*\}\s*\n(.*?)(?=\n\\section\*?|\n\\end\{document\}|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        match = pattern.search(self.raw_text)
        return match.group(1).strip() if match else ""

  @staticmethod
  def extract_skills_dict(latex_text: str) -> dict:
    """Parses skill category pairs whether written in tabularx or itemize format.

    Returns a dict: {"Category Name": "Skill Items"}
    """
    skills_dict = {}

    # Case 1: Extract from \begin{tabularx} ... \end{tabularx}
    tabularx_match = re.search(
        r"\\begin\{tabularx\}.*?\n?(.*?)\\end\{tabularx\}", latex_text, re.DOTALL
    )
    if tabularx_match:
      table_content = tabularx_match.group(1).strip()
      rows = table_content.split(r"\\")
      for row in rows:
        row = row.strip()
        if "&" in row:
          parts = row.split("&", 1)

          # Clean category name (strip \textbf{}, colons, LaTeX macros)
          category = re.sub(r"\\textbf\{([^}]+)\}", r"\1", parts[0]).strip()
          category = category.rstrip(":").strip()

          # Clean skill values
          skills_val = parts[1].strip()

          if category and skills_val:
            skills_dict[category] = skills_val

      if skills_dict:
        return skills_dict

    # Case 2: Extract from \begin{itemize} ... \end{itemize}
    itemize_match = re.search(
        r"\\begin\{itemize\}.*?\n?(.*?)\\end\{itemize\}", latex_text, re.DOTALL
    )
    if itemize_match:
      itemize_content = itemize_match.group(1).strip()
      for line in itemize_content.split("\n"):
        line = line.strip()
        if line.startswith(r"\item"):
          match = re.search(r"\\item\s+\\textbf\{([^}]+)\:?\}\s*(.*)", line)
          if match:
            category = match.group(1).rstrip(":").strip()
            skills_val = match.group(2).strip()
            skills_dict[category] = skills_val

    return skills_dict
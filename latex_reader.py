import re
from typing import Any, Dict, List, Optional

from tqdm import tqdm


class LaTeXReader:
  """Specialized LaTeX CV Reader designed to parse structured sections

  (Education, Professional Experience, Projects, Technical Skills) 
  handling both \\begin{itemize}...\\end{itemize} and tabular/tabularx environments.
  """

  def __init__(self, raw_text: str):
    self.raw_text = raw_text
    self.sections = self._extract_sections()

  def _extract_sections(self) -> Dict[str, str]:
    """Extracts top-level LaTeX sections based on \\section{...} or \\section*{...}."""
    section_pattern = re.compile(r"\\section\*?\{([^}]+)\}", re.IGNORECASE)
    matches = list(section_pattern.finditer(self.raw_text))
    
    sections = {}
    if not matches:
      sections["full_document"] = self.raw_text
      return sections

    for i, match in tqdm(enumerate(matches),desc="extract_sections",leave=False):
      sec_title = match.group(1).strip().lower()
      start_idx = match.end()
      end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(self.raw_text)
      sections[sec_title] = self.raw_text[start_idx:end_idx].strip()

    return sections

  def get_section_content(self, section_name: str) -> Optional[str]:
    """Returns the raw text content of a specific section."""
    key = section_name.strip().lower()
    return self.sections.get(key)

  def parse_structured_entries(self, section_name: str) -> List[Dict[str, Any]]:
    """Parses a section (such as Education, Experience, or Projects) into structured items.

    Each item is keyed by:
      - 'title': Text inside the primary \\textbf{...}
      - 'metadata': Subtitle, institution, or date line following the title before the itemize block
      - 'bullet_points': List of items extracted from \\begin{itemize} ... \\end{itemize}
    """
    content = self.get_section_content(section_name)
    if not content:
      return []

    # If the section uses a tabular or tabularx environment (e.g., Technical Skills), parse it as tabular data
    if "\\begin{tabular" in content:
      return self._parse_tabular_entries(content)

    entry_pattern = re.compile(r"\\textbf\{([^}]+)\}", re.IGNORECASE)
    matches = list(entry_pattern.finditer(content))

    if not matches:
      return [{"title": "General", "metadata": "", "bullet_points": self._extract_bullets(content)}]

    entries = []
    for i, match in enumerate(matches):
      title = match.group(1).strip()
      start_idx = match.end()
      end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)
      
      block_text = content[start_idx:end_idx].strip()
      
      bullet_points = self._extract_bullets(block_text)
      
      metadata_text = re.sub(r"\\begin\{itemize\}.*?\\end\{itemize\}", "", block_text, flags=tr.DOTALL) if 'tr' in globals() else re.sub(r"\\begin\{itemize\}.*?\\end\{itemize\}", "", block_text, flags=re.DOTALL)
      metadata_text = re.sub(r"\\[a-zA-Z]+\*?(?:\{[^}]*\})?", "", metadata_text)
      metadata_text = " ".join(metadata_text.split()).strip()

      entries.append({
          "title": title,
          "metadata": metadata_text,
          "bullet_points": bullet_points
      })

    return entries

  def _parse_tabular_entries(self, content: str) -> List[Dict[str, Any]]:
    """Parses tabular/tabularx environments into structured category-value entries."""
    tabular_pattern = re.compile(r"\\begin\{tabularx?\}(?:\{[^}]*\})*\{([^}]*\})(.*?)\\end\{tabularx?\}", re.DOTALL)
    matches = tabular_pattern.findall(content)
    
    entries = []
    for _, table_body in matches:
      rows = table_body.split(r"\\")
      for row in rows:
        if "&" in row:
          parts = row.split("&", 1)
          category = self._clean_latex_syntax(parts[0])
          items_text = self._clean_latex_syntax(parts[1])
          
          # Split items by comma or bullet points if applicable
          items_list = [item.strip() for item in items_text.split(",") if item.strip()]
          
          if category:
            entries.append({
                "title": category,
                "metadata": "",
                "bullet_points": items_list if items_list else [items_text]
            })
            
    return entries if entries else [{"title": "Technical Skills", "metadata": "", "bullet_points": [content]}]

  def _extract_bullets(self, text: str) -> List[str]:
    """Extracts all \\item contents from any \\begin{itemize} blocks within the text."""
    itemize_pattern = re.compile(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", re.DOTALL)
    item_pattern = re.compile(r"\\item\s+(.*?)(?=\\item|\\end\{itemize\}|$)", re.DOTALL)
    
    bullets = []
    itemize_matches = itemize_pattern.findall(text)
    
    for block in itemize_matches:
      raw_items = item_pattern.findall(block)
      for item in raw_items:
        cleaned = self._clean_latex_syntax(item)
        if cleaned:
          bullets.append(cleaned)
          
    return bullets

  def _clean_latex_syntax(self, text: str) -> str:
    """Removes or normalizes common LaTeX markup in text."""
    text = re.sub(r"\\textbf\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\href\{[^}]+\}\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\{[^}]*\})?", "", text)
    text = text.replace("\\%", "%").replace("\\&", "&")
    return " ".join(text.split()).strip()

  def parse_education(self) -> List[Dict[str, Any]]:
    return self.parse_structured_entries("education")

  def parse_experience(self) -> List[Dict[str, Any]]:
    for key in ["professional experience", "experience"]:
      if key in self.sections:
        return self.parse_structured_entries(key)
    return []

  def parse_projects(self) -> List[Dict[str, Any]]:
    for key in ["projects", "selected projects", "data & systems projects"]:
      if key in self.sections:
        return self.parse_structured_entries(key)
    return []

  def parse_technical_skills(self) -> List[Dict[str, Any]]:
    for key in ["technical skills", "skills"]:
      if key in self.sections:
        return self.parse_structured_entries(key)
    return []
import re
from typing import Any, Dict, List, Optional
import logging
import calendar


from config import enablelog
if enablelog:
  logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

from university_validator import UniversityValidator

class LaTeXReader:
  """Specialized LaTeX CV Reader designed to parse structured sections
  and document metadata natively without comment stripping.
  """

  def __init__(self, raw_text: str):
    self.raw_text = raw_text
    self.sections = self._extract_sections()
    self.validator = UniversityValidator()
    
  def _extract_sections(self) -> Dict[str, str]:
    """Extracts top-level LaTeX sections based on \section{...} or \section*{...}."""
    section_pattern = re.compile(r"\\section\*?\{([^}]+)\}", re.IGNORECASE)
    matches = list(section_pattern.finditer(self.raw_text))
    
    sections = {}
    if not matches:
      sections["full_document"] = self.raw_text
      return sections

    for i, match in enumerate(matches):
      sec_title = match.group(1).strip().lower()
      start_idx = match.end()
      end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(self.raw_text)
      sections[sec_title] = self.raw_text[start_idx:end_idx].strip()

    return sections

  def get_section_content(self, section_name: str) -> Optional[str]:
    """Returns the raw text content of a specific section."""
    key = section_name.strip().lower()
    return self.sections.get(key)

  def parse_candidate_name(self) -> str:
    author_match = re.search(r"\\author\{([^}]+)\}", self.raw_text)
    if author_match:
      return self._clean_latex_syntax(author_match.group(1))

    header_block = self.raw_text[:1500]
    name_match = re.search(r"\\textbf\{\s*([A-Z][a-zA-Z\s]+)\s*\}", header_block)
    if name_match:
      return self._clean_latex_syntax(name_match.group(1))
    return ""

  def parse_contact_info(self) -> str:
    header_block = self.raw_text[:2000]
    contacts = []

    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", header_block)
    if email_match:
      contacts.append(email_match.group(0))

    phone_match = re.search(r"(\+?[0-9\-\s\(\)]{7,15})", header_block)
    if phone_match:
      contacts.append(phone_match.group(0).strip())

    linkedin_match = re.search(r"(?:linkedin\.com/in/[^\s}]+|\\href\{([^}]+linkedin[^\}]+)\})", header_block, re.IGNORECASE)
    if linkedin_match:
      url = linkedin_match.group(1) if linkedin_match.lastindex else linkedin_match.group(0)
      contacts.append(self._clean_latex_syntax(url))

    return " | ".join(contacts)

  def parse_summary(self) -> List[str]:
    summaries = []
    for sec_key, sec_val in self.sections.items():
      if any(k in sec_key for k in ["summary", "profile", "objective", "about"]):
        clean_text = self._clean_latex_syntax(sec_val)
        if clean_text:
          summaries.append(clean_text)
    return summaries

  def _is_valid_month(self, month_str: str) -> bool:
    full_months = {m.lower() for m in calendar.month_name[1:]}
    abbrev_months = {m.lower() for m in calendar.month_abbr[1:]}
    return month_str.lower() in full_months or month_str.lower() in abbrev_months

  def _extract_dates(self, text: str) -> tuple[str, str]:
    if not text:
      return "", ""
      
    date_range_pattern = re.compile(
        r'([A-Za-z]+\s+\d{4}|\d{4})\s*(?:–|--|-|to)\s*([A-Za-z]+\s+\d{4}|\d{4}|Present|Current)', 
        re.IGNORECASE
    )
    match = date_range_pattern.search(text)
    if not match:
      return "", ""
      
    start_raw, end_raw = match.groups()
    
    def validate_and_format(date_str: str) -> str:
      if date_str.lower() in ["present", "current"]:
        return date_str.capitalize()
        
      parts = date_str.split()
      if len(parts) == 2:
        month_part, year_part = parts
        if self._is_valid_month(month_part):
          return f"{month_part} {year_part}"
          
      return date_str

    return validate_and_format(start_raw), validate_and_format(end_raw)

  

  def _is_valid_location_name(self, text: str) -> bool:
    """Lightning-fast check to ensure the token looks like a real location 
    using a compact set of common global regions and pattern matching.
    """
    cleaned = text.strip().lower()
    if not cleaned:
      return False
      
    # Common global hubs, countries, and remote options
    common_locations = {
        "usa", "uk", "us", "united states", "united kingdom", "singapore", "thailand", 
        "myanmar", "burma", "japan", "germany", "france", "canada", "australia", "china", 
        "india", "vietnam", "malaysia", "indonesia", "philippines", "taiwan", "south korea",
        "yangon", "mandalay", "bangkok", "tokyo", "london", "new york", "san francisco", 
        "singapore", "remote", "hybrid", "onsite"
    }
    
    if cleaned in common_locations:
      return True
      
    # Check standard regional patterns like "City, State" (e.g., "San Francisco, CA") 
    # or comma-separated country codes (e.g., "City, TH")
    if re.search(r',\s*[A-Z]{2}$', text.strip()):
      return True
      
    # If it contains common location terms or multiple words ending with a known country/state
    parts = [p.strip().lower() for p in cleaned.split(',')]
    if len(parts) > 1 and parts[-1] in common_locations:
      return True
      
    return False

  def _extract_metadata_intelligently(self, raw_metadata: str) -> Dict[str, str]:
    """Intelligently cleans metadata, extracts dates, and separates 
    Company Name and Location without date bleed.
    """
    if not raw_metadata:
      return {"company": "", "location": "", "from": "", "to": ""}

    cleaned_block = self._clean_latex_syntax(raw_metadata)
    
    # 1. Extract dates
    from_date, to_date = self._extract_dates(raw_metadata)

    # 2. Remove the extracted date substring from the raw block if present
    date_range_pattern = re.compile(
        r'([A-Za-z]+\s+\d{4}|\d{4})\s*(?:–|--|-|to)\s*([A-Za-z]+\s+\d{4}|\d{4}|Present|Current)', 
        re.IGNORECASE
    )
    cleaned_block = date_range_pattern.sub('', cleaned_block)
    
    # Clean up remaining separators (\hfill, dashes, percentages, etc.)
    cleaned_block = re.sub(r'\\hfill', ' ', cleaned_block)
    cleaned_block = re.sub(r'%', '', cleaned_block)
    
    # 3. Split remaining chunks into Company and Location
    chunks = [c.strip() for c in re.split(r'\\\\|\n|,|-', cleaned_block) if c.strip()]
    
    company_candidate = chunks[0] if chunks else ""
    location_candidate = chunks[1] if len(chunks) > 1 else ""

    return {
        "company": company_candidate,
        "location": location_candidate,
        "from": from_date,
        "to": to_date
    }
  
  def parse_structured_entries(self, section_name: str) -> List[Dict[str, Any]]:
    content = self.get_section_content(section_name)
    if not content:
      return []

    if "\\begin{tabular" in content:
      return self._parse_tabular_entries(content)

    rsub_pattern = re.compile(r"\\begin\{rSubsection\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}\{([^}]*)\}(.*?)\\end\{rSubsection\}", re.DOTALL)
    rsub_matches = list(rsub_pattern.finditer(content))
    if rsub_matches:
      entries = []
      for m in rsub_matches:
        title, metadata, company, location, block_text = m.groups()
        bullets = self._extract_bullets(block_text)
        combined_text = f"{title} {metadata} {company} {location} {block_text}"
        from_date, to_date = self._extract_dates(combined_text)
        entries.append({
            "title": self._clean_latex_syntax(title),
            "metadata": f"{self._clean_latex_syntax(company)} - {self._clean_latex_syntax(location)} ({self._clean_latex_syntax(metadata)})".strip(" -()"),
            "from": from_date,
            "to": to_date,
            "bullet_points": bullets
        })
      return entries

    entry_pattern = re.compile(r"\\textbf\{([^}]+)\}", re.IGNORECASE)
    matches = list(entry_pattern.finditer(content))

    if not matches:
      from_date, to_date = self._extract_dates(content)
      return [{"title": "General", "metadata": "", "from": from_date, "to": to_date, "bullet_points": self._extract_bullets(content)}]

    entries = []
    for i, match in enumerate(matches):
      title = match.group(1).strip()
      start_idx = match.end()
      end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)
      
      block_text = content[start_idx:end_idx].strip()
      bullet_points = self._extract_bullets(block_text)
      
      metadata_text = re.sub(r"\\begin\{itemize\}.*?\\end\{itemize\}", "", block_text, flags=re.DOTALL)
      metadata_text = " ".join(metadata_text.split()).strip()

      combined_text = f"{title} {metadata_text} {block_text}"
      from_date, to_date = self._extract_dates(combined_text)

      entries.append({
          "title": self._clean_latex_syntax(title),
          "metadata": metadata_text,
          "from": from_date,
          "to": to_date,
          "bullet_points": bullet_points
      })

    return entries

  def _parse_tabular_entries(self, content: str) -> List[Dict[str, Any]]:
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
          items_list = [item.strip() for item in items_text.split(",") if item.strip()]
          
          if category:
            entries.append({
                "title": category,
                "metadata": "",
                "from": "",
                "to": "",
                "bullet_points": items_list if items_list else [items_text]
            })
            
    return entries if entries else [{"title": "Technical Skills", "metadata": "", "from": "", "to": "", "bullet_points": [content]}]

  def _extract_bullets(self, text: str) -> List[str]:
    itemize_pattern = re.compile(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", re.DOTALL)
    item_pattern = re.compile(r"\\item\s+(.*?)(?=\\item|\\end\{itemize\}|$)", re.DOTALL)
    
    bullets = []
    for block in itemize_pattern.findall(text):
      for item in item_pattern.findall(block):
        cleaned = self._clean_latex_syntax(item)
        if cleaned:
          bullets.append(cleaned)
    return bullets

  def _clean_latex_syntax(self, text: str) -> str:
    text = re.sub(r"\\textbf\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\href\{[^}]+\}\{([^}]+)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\{[^}]*\})?", "", text)
    return text.replace("\\%", "%").replace("\\&", "&").replace("\\\\", " ").strip()

  def parse_education(self) -> List[Dict[str, Any]]:
    raw_edu = self.parse_structured_entries("education")
    formatted_edu = []
    
    for edu in raw_edu:
      title = edu.get("title", "")
      metadata = edu.get("metadata", "")
      from_date = edu.get("from", "")
      to_date = edu.get("to", "")
      combined_text = f"{title} {metadata}"
      
      matched_institution = ""
      for uni in self.validator.universities:
        if uni.lower() in combined_text.lower():
          matched_institution = uni
          break
          
      if not matched_institution:
        for known_inst in ["Asian Institute of Technology", "Technological University"]:
          if known_inst.lower() in combined_text.lower():
            matched_institution = known_inst
            break

      is_valid = bool(matched_institution) or self.validator.isValidatedUniversity(metadata)
      institution_name = matched_institution if matched_institution else self._clean_institution_name(metadata)

      if is_valid and title and not any(kw in title.lower() for kw in ["coursework", "thesis", "specialization"]):
        formatted_edu.append({
            "degree": title,
            "institution": institution_name,
            "from": from_date,
            "to": to_date,
            "coursework": edu.get("bullet_points", []),
            "thesis": ""
        })
        
    return formatted_edu

  def _clean_institution_name(self, text: str) -> str:
    text = re.sub(r"^[\s,\-\%]+", "", text)
    text = re.split(r"[%]", text)[0]
    return " ".join(text.split()).strip()
  
  def parse_experience(self) -> List[Dict[str, Any]]:
    raw_experience = []
    for key in ["professional experience", "experience", "work experience", "employment"]:
      if key in self.sections:
        raw_experience = self.parse_structured_entries(key)
        break
        
    ignored_titles = {"key achievements", "summary", "responsibilities", "skills", "overview"}
    
    formatted_experience = []
    for exp in raw_experience:
      title = exp.get("title", "").strip()
      
      # Skip non-job header blocks
      if not title or title.lower() in ignored_titles:
        continue
        
      meta_info = self._extract_metadata_intelligently(exp.get("metadata", ""))
      
      from_date = exp.get("from") or meta_info["from"]
      to_date = exp.get("to") or meta_info["to"]

      formatted_experience.append({
          "title": title,
          "metadata": meta_info["company"],
          "location": meta_info["location"],
          "from": from_date,
          "to": to_date,
          "bullet_points": exp.get("bullet_points", [])
      })
      
    return formatted_experience
  
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

  def parse_certificates(self) -> List[Dict[str, Any]]:
    for key in ["certifications", "certification", "certificates", "certificate"]:
      content = self.get_section_content(key)
      if content:
        entries = []
        lines = re.split(r'\\\\\s*|\n', content)
        
        # Ignored LaTeX artifacts or unwanted text headers
        ignored_tokens = {"[leftmargin=*", "certificates", "certifications", "skills"}
        
        for line in lines:
          line_str = line.strip()
          if not line_str or line_str.startswith('%'):
            continue
            
          # Clean LaTeX syntax first to check its true value
          cleaned = self._clean_latex_syntax(line_str)
          
          # Skip structural LaTeX elements or headers
          if not cleaned or any(cleaned.lower().startswith(token) for token in ignored_tokens):
            continue
          
          from_date, to_date = self._extract_dates(line_str)
          
          entries.append({
              "certificate_name": cleaned,
              "certificate_id": "",
              "from": from_date,
              "to": to_date,
              "url": "",
              "bullet_points": []
          })
        return entries
    return []

  def parse_languages(self) -> List[str]:
    """Parses the languages section into a clean list of language proficiencies."""
    for key in ["languages", "language"]:
      content = self.get_section_content(key)
      if content:
        languages = []
        lines = re.split(r'\\\\\s*|\n', content)
        ignored_tokens = {"[leftmargin=*", "languages", "language"}
        
        for line in lines:
          line_str = line.strip()
          if not line_str or line_str.startswith('%'):
            continue
          
          cleaned = self._clean_latex_syntax(line_str)
          if cleaned and not any(cleaned.lower().startswith(token) for token in ignored_tokens):
            languages.append(cleaned)
        return languages
    return []

  def parse_core_competencies(self) -> List[str]:
    """Parses the core competencies section into a clean list of competencies."""
    for key in ["core competencies", "competencies", "key competencies"]:
      content = self.get_section_content(key)
      if content:
        # Core competencies are usually standard itemize lists
        return self._extract_bullets(content)
    return []
import os
import sqlite3
from typing import Any, Dict, List, Optional


class SQLiteCRUD:
  """Encapsulates SQLite database operations for CV profile management,

  supporting section-specific inserts for summary, education, experience, projects, 
  certificates, languages, technical skills, core competencies, and contact info.
  """

  def __init__(self, db_path: str):
    self.db_path = db_path
    self.conn = self._init_sqlite_db()

  def _init_sqlite_db(self) -> sqlite3.Connection:
    db_dir = os.path.dirname(os.path.abspath(self.db_path))
    if db_dir:
      os.makedirs(db_dir, exist_ok=True)
      
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS scanned_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            file_path TEXT,
            mtime REAL,
            modified_date TEXT
        );

        CREATE TABLE IF NOT EXISTS contact_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            email TEXT UNIQUE,
            phone TEXT,
            linkedin TEXT,
            github TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS education (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            degree TEXT,
            institution TEXT,
            "from" TEXT,
            "to" TEXT,
            coursework TEXT,
            thesis TEXT,
            UNIQUE(candidate_name, institution, "from")
        );

        CREATE TABLE IF NOT EXISTS experience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            job_title TEXT,
            company TEXT,
            "from" TEXT,
            "to" TEXT,
            details TEXT,
            UNIQUE(candidate_name, company, "from")
        );

        CREATE TABLE IF NOT EXISTS summary_and_job (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            summary TEXT,
            target_job TEXT,
            source_file TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            project_name TEXT,
            tech_stack TEXT,
            details TEXT,
            UNIQUE(candidate_name, project_name)
        );

        CREATE TABLE IF NOT EXISTS certifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            certificate_name TEXT,
            issuing_organization TEXT,
            certificate_id TEXT,
            "from" TEXT,
            "to" TEXT,
            url TEXT,
            skills TEXT,
            media_picture TEXT,
            UNIQUE(candidate_name, certificate_name)
        );

        CREATE TABLE IF NOT EXISTS languages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            language TEXT,
            UNIQUE(candidate_name, language)
        );

        CREATE TABLE IF NOT EXISTS technical_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            target_role TEXT,
            source_file TEXT,
            category TEXT,
            skills TEXT,
            UNIQUE(target_role, source_file, category)
        );

        CREATE TABLE IF NOT EXISTS core_competencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            target_role TEXT,
            source_file TEXT,
            competencies TEXT,
            UNIQUE(target_role, source_file)
        );
      """)
    conn.commit()
    return conn

  def upsert_scanned_file(
      self,
      filename: str,
      file_path: str,
      mtime: float,
      formatted_date: str,
  ):
    cursor = self.conn.cursor()
    cursor.execute(
        """
        INSERT INTO scanned_files (filename, file_path, mtime, modified_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(filename) DO UPDATE SET file_path=?, mtime=?, modified_date=?
    """,
        (filename, file_path, mtime, formatted_date, file_path, mtime, formatted_date),
    )
    self.conn.commit()

  def get_file_mtime(self, filename: str) -> Optional[float]:
    cursor = self.conn.cursor()
    cursor.execute("SELECT mtime FROM scanned_files WHERE filename = ?", (filename,))
    row = cursor.fetchone()
    return row[0] if row else None

  def store_contact_info(self, parsed_data: Dict[str, Any]):
    """Stores or updates contact information in SQLite, avoiding duplicate rows by email."""
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    email = parsed_data.get("email", "").strip()
    phone = parsed_data.get("phone", "").strip()
    linkedin = parsed_data.get("linkedin", "").strip()
    github = parsed_data.get("github", "").strip()

    if email or candidate_name:
      cursor.execute(
          """
          INSERT INTO contact_info (candidate_name, email, phone, linkedin, github)
          VALUES (?, ?, ?, ?, ?)
          ON CONFLICT(email) DO UPDATE SET
              candidate_name=excluded.candidate_name,
              phone=excluded.phone,
              linkedin=excluded.linkedin,
              github=excluded.github,
              updated_at=CURRENT_TIMESTAMP
      """,
          (candidate_name, email, phone, linkedin, github),
      )
      self.conn.commit()

  def store_summary_section(self, parsed_data: Dict[str, Any], source_file: str):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    summaries = parsed_data.get("summaries", [])
    summary_text = "\n".join(summaries) if summaries else ""
    target_job = parsed_data.get("target_role", "") or candidate_name
    
    if summary_text or target_job:
      cursor.execute(
          """
          INSERT INTO summary_and_job (candidate_name, summary, target_job, source_file)
          VALUES (?, ?, ?, ?)
          ON CONFLICT(source_file) DO UPDATE SET
              candidate_name=excluded.candidate_name,
              summary=excluded.summary,
              target_job=excluded.target_job
      """,
          (candidate_name, summary_text, target_job, source_file),
      )
      self.conn.commit()

  

  def store_projects_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    
    for proj in parsed_data.get("projects", []):
      if isinstance(proj, dict):
        project_name = proj.get("project_name", "").strip()
        tech_stack = proj.get("tech_stack", "")
        if isinstance(tech_stack, list):
          import json
          tech_stack = json.dumps(tech_stack)
          
        details = proj.get("details", "")
        if isinstance(details, list):
          import json
          details = json.dumps(details)

        if project_name:
          cursor.execute(
              """
              INSERT INTO projects (candidate_name, project_name, tech_stack, details)
              VALUES (?, ?, ?, ?)
              ON CONFLICT(candidate_name, project_name) DO UPDATE SET
                  tech_stack=excluded.tech_stack,
                  details=excluded.details
          """,
              (candidate_name, project_name, tech_stack, details),
          )
    self.conn.commit()

  def store_certificate_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    for cert in parsed_data.get("certifications", []):
      if isinstance(cert, dict):
        cert_name = cert.get("certificate_name", "").strip()
        issuing_org = cert.get("issuing_organization", "").strip()
        cert_id = cert.get("certificate_id", "").strip()
        from_date = cert.get("from", "").strip()
        to_date = cert.get("to", "").strip()
        url = cert.get("url", "").strip()
        
        import json
        skills = json.dumps(cert.get("skills", []))
        media_picture = cert.get("media_picture", "").strip()

        if cert_name:
          cursor.execute(
              """
              INSERT INTO certifications (
                  candidate_name, certificate_name, issuing_organization, 
                  certificate_id, "from", "to", url, skills, media_picture
              )
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
              ON CONFLICT(candidate_name, certificate_name) DO UPDATE SET
                  issuing_organization=excluded.issuing_organization,
                  certificate_id=excluded.certificate_id,
                  "from"=excluded."from",
                  "to"=excluded."to",
                  url=excluded.url,
                  skills=excluded.skills,
                  media_picture=excluded.media_picture
          """,
              (candidate_name, cert_name, issuing_org, cert_id, from_date, to_date, url, skills, media_picture),
          )
    self.conn.commit()

  def store_language_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    for lang in parsed_data.get("languages", []):
      lang_str = lang.strip()
      if lang_str:
        cursor.execute(
            """
            INSERT INTO languages (candidate_name, language)
            VALUES (?, ?)
            ON CONFLICT(candidate_name, language) DO NOTHING
        """,
            (candidate_name, lang_str),
        )
    self.conn.commit()

  def store_core_competencies_section(self, parsed_data: Dict[str, Any], source_file: str):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    target_role = parsed_data.get("target_role", "").strip() or candidate_name

    core_comp = parsed_data.get("core_competencies", [])
    if core_comp:
      comp_str = ", ".join(core_comp) if isinstance(core_comp, list) else str(core_comp)
      cursor.execute(
          """
          INSERT INTO core_competencies (candidate_name, target_role, source_file, competencies)
          VALUES (?, ?, ?, ?)
          ON CONFLICT(target_role, source_file) DO UPDATE SET
              candidate_name=excluded.candidate_name,
              competencies=excluded.competencies
      """,
          (candidate_name, target_role, source_file, comp_str),
      )
      self.conn.commit()

  def store_skills_section(self, parsed_data: Dict[str, Any], source_file: str):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    target_role = parsed_data.get("target_role", "").strip() or candidate_name

    tech_skills = parsed_data.get("technical_skills", {})
    if isinstance(tech_skills, dict):
      for category, skills in tech_skills.items():
        skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)
        cursor.execute(
            """
            INSERT INTO technical_skills (candidate_name, target_role, source_file, category, skills)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(target_role, source_file, category) DO UPDATE SET
                candidate_name=excluded.candidate_name,
                skills=excluded.skills
        """,
            (candidate_name, target_role, source_file, category, skills_str),
        )
    self.conn.commit()

  def clear_all(self):
    cursor = self.conn.cursor()
    for tbl in [
        "scanned_files",
        "contact_info",
        "education",
        "experience",
        "summary_and_job",
        "projects",
        "certifications",
        "languages",
        "technical_skills",
        "core_competencies",
    ]:
      cursor.execute(f"DELETE FROM {tbl}")
    self.conn.commit()

  def store_education_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    for edu in parsed_data.get("education", []):
      degree = edu.get("degree", "").strip()
      institution = edu.get("institution", "").strip()
      from_date = (edu.get("from", "") or edu.get("from_date", "") or edu.get("dates", "")).strip()
      to_date = edu.get("to", "").strip()
      import json
      coursework = json.dumps(edu.get("coursework", []))
      thesis = edu.get("thesis", "").strip()
      
      if degree or institution:
        cursor.execute(
            """
            INSERT INTO education (candidate_name, degree, institution, [from], [to], coursework, thesis)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_name, institution, [from]) DO UPDATE SET
                degree = COALESCE(NULLIF(excluded.degree, ''), education.degree),
                [to] = CASE 
                    WHEN education.[to] LIKE '%Present%' THEN education.[to]
                    WHEN excluded.[to] IS NULL OR excluded.[to] = '' THEN education.[to]
                    ELSE excluded.[to] 
                END,
                coursework = CASE 
                    WHEN excluded.coursework IS NULL OR excluded.coursework = '[]' OR excluded.coursework = '' THEN education.coursework
                    ELSE excluded.coursework 
                END,
                thesis = CASE 
                    WHEN excluded.thesis IS NULL OR excluded.thesis = '' THEN education.thesis
                    ELSE excluded.thesis 
                END
        """,
            (candidate_name, degree, institution, from_date, to_date, coursework, thesis),
        )
    self.conn.commit()

  def store_experience_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    for exp in parsed_data.get("work_experience", []):
      job_title = exp.get("job_title", "").strip()
      company = exp.get("company", "").strip()
      from_date = exp.get("from", "").strip()
      to_date = exp.get("to", "").strip()
      
      import json
      details_list = exp.get("bullet_points", [])
      details_text = json.dumps(details_list) if isinstance(details_list, list) else str(details_list)
      
      if job_title or company:
        cursor.execute(
            """
            INSERT INTO experience (candidate_name, job_title, company, [from], [to], details)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_name, company, [from]) DO UPDATE SET
                job_title = COALESCE(NULLIF(excluded.job_title, ''), experience.job_title),
                [to] = CASE 
                    WHEN experience.[to] LIKE '%Present%' THEN experience.[to]
                    WHEN excluded.[to] IS NULL OR excluded.[to] = '' THEN experience.[to]
                    ELSE excluded.[to] 
                END,
                details = CASE 
                    WHEN excluded.details IS NULL OR excluded.details = '[]' OR excluded.details = '' THEN experience.details
                    ELSE excluded.details 
                END
        """,
            (candidate_name, job_title, company, from_date, to_date, details_text),
        )
    self.conn.commit()

  def get_contact_info(self) -> dict:
    cursor = self.conn.cursor()
    cursor.execute("SELECT candidate_name, email, phone, linkedin, github FROM contact_info LIMIT 1")
    row = cursor.fetchone()
    if row:
      return {
          "candidate_name": row[0],
          "email": row[1],
          "phone": row[2],
          "linkedin": row[3],
          "github": row[4]
      }
    return {"candidate_name": "Sat Naing Tun", "email": "", "phone": "", "linkedin": "", "github": ""}

  def get_summary(self) -> str:
    cursor = self.conn.cursor()
    cursor.execute("SELECT summary FROM summary_and_job LIMIT 1")
    row = cursor.fetchone()
    return row[0] if row and row[0] else ""

  def get_education(self) -> list:
    cursor = self.conn.cursor()
    cursor.execute('SELECT degree, institution, "from", "to", coursework, thesis FROM education')
    education_list = []
    import json
    for row in cursor.fetchall():
      try:
        cw = json.loads(row[4]) if row[4] else []
      except Exception:
        cw = []
      education_list.append({
          "degree": row[0],
          "institution": row[1],
          "from": row[2],
          "to": row[3],
          "coursework": cw,
          "thesis": row[5]
      })
    return education_list

  def get_experience(self) -> list:
    cursor = self.conn.cursor()
    cursor.execute('SELECT job_title, company, "from", "to", details FROM experience')
    experience_list = []
    import json
    for row in cursor.fetchall():
      try:
        bullets = json.loads(row[4]) if row[4] else []
      except Exception:
        bullets = [row[4]] if row[4] else []
      experience_list.append({
          "title": row[0],
          "company": row[1],
          "from": row[2],
          "to": row[3],
          "bullet_points": bullets
      })
    return experience_list

  def get_projects(self) -> list:
    cursor = self.conn.cursor()
    cursor.execute('SELECT project_name, tech_stack, details FROM projects')
    projects_list = []
    import json
    for row in cursor.fetchall():
      try:
        ts = json.loads(row[1]) if row[1] else []
      except Exception:
        ts = []
      try:
        det = json.loads(row[2]) if row[2] else []
      except Exception:
        det = [row[2]] if row[2] else []
      projects_list.append({
          "project_name": row[0],
          "tech_stack": ts,
          "details": det
      })
    return projects_list

  def get_certifications(self) -> list:
    cursor = self.conn.cursor()
    cursor.execute('SELECT certificate_name, issuing_organization, "from", "to", url FROM certifications')
    cert_list = []
    for row in cursor.fetchall():
      cert_list.append({
          "certificate_name": row[0],
          "issuing_organization": row[1],
          "from": row[2],
          "to": row[3],
          "url": row[4]
      })
    return cert_list

  def get_languages(self) -> list:
    cursor = self.conn.cursor()
    cursor.execute('SELECT language FROM languages')
    return [row[0] for row in cursor.fetchall()]

  def get_core_competencies(self) -> list:
    cursor = self.conn.cursor()
    cursor.execute('SELECT competencies FROM core_competencies LIMIT 1')
    row = cursor.fetchone()
    if row and row[0]:
      return [c.strip() for c in row[0].split(",")]
    return []

  def get_technical_skills(self) -> dict:
    cursor = self.conn.cursor()
    cursor.execute('SELECT category, skills FROM technical_skills')
    skills_dict = {}
    for row in cursor.fetchall():
      cat, sk_str = row[0], row[1]
      skills_dict[cat] = [s.strip() for s in sk_str.split(",") if s.strip()]
    return skills_dict

  def close(self):
    if self.conn:
      self.conn.close()
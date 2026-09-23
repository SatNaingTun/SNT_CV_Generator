import os
import sqlite3
from typing import Any, Dict, List, Optional


class SQLiteCRUD:
  """Encapsulates SQLite database operations for CV profile management,

  supporting section-specific inserts for summary, education, experience, projects, 
  certificates, languages, and technical skills / core competencies.
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

        CREATE TABLE IF NOT EXISTS education (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            degree TEXT,
            institution TEXT,
            "from" TEXT,
            "to" TEXT,
            coursework TEXT,
            thesis TEXT,
            UNIQUE(candidate_name, degree, institution, "from", "to")
        );

        CREATE TABLE IF NOT EXISTS experience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_name TEXT,
            job_title TEXT,
            company TEXT,
            "from" TEXT,
            "to" TEXT,
            details TEXT,
            UNIQUE(candidate_name, job_title, company, "from", "to")
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
            certificate_id TEXT,
            "from" TEXT,
            "to" TEXT,
            url TEXT,
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
            INSERT INTO education (candidate_name, degree, institution, "from", "to", coursework, thesis)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_name, degree, institution, "from", "to") DO UPDATE SET
                coursework=excluded.coursework,
                thesis=excluded.thesis
        """,
            (candidate_name, degree, institution, from_date, to_date, coursework, thesis),
        )
    self.conn.commit()

  def store_project_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    for proj in parsed_data.get("projects", []):
      project_name = proj.get("project_name", "").strip()
      import json
      tech_stack = json.dumps(proj.get("tech_stack", []))
      details_list = proj.get("details", [])
      details_text = "\n".join(details_list) if isinstance(details_list, list) else str(details_list)
      if project_name:
        cursor.execute(
            """
            INSERT INTO projects (candidate_name, project_name, tech_stack, details)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(candidate_name, project_name) DO UPDATE SET
                tech_stack=excluded.tech_stack,
                details=excluded.details
        """,
            (candidate_name, project_name, tech_stack, details_text),
        )
    self.conn.commit()

  def store_certificate_section(self, parsed_data: Dict[str, Any]):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    for cert in parsed_data.get("certifications", []):
      if isinstance(cert, str):
        cert_name = cert.strip()
        cert_id, from_date, to_date, url = "", "", "", ""
      elif isinstance(cert, dict):
        cert_name = cert.get("certificate_name", "").strip()
        cert_id = cert.get("certificate_id", "").strip()
        from_date = (cert.get("from", "") or cert.get("from_date", "") or cert.get("date", "")).strip()
        to_date = cert.get("to", "").strip()
        url = cert.get("url", "").strip()
      else:
        continue

      if cert_name:
        cursor.execute(
            """
            INSERT INTO certifications (candidate_name, certificate_name, certificate_id, "from", "to", url)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_name, certificate_name) DO UPDATE SET
                certificate_id=excluded.certificate_id,
                "from"=excluded."from",
                "to"=excluded."to",
                url=excluded.url
        """,
            (candidate_name, cert_name, cert_id, from_date, to_date, url),
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

  def store_skills_section(self, parsed_data: Dict[str, Any], source_file: str):
    cursor = self.conn.cursor()
    candidate_name = parsed_data.get("candidate_name", "").strip()
    target_role = parsed_data.get("target_role", "").strip() or candidate_name

    # 1. Technical Skills (Stored category-wise, skills comma-separated)
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

    # 2. Core Competencies (Stored comma-separated text)
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

  def clear_all(self):
    cursor = self.conn.cursor()
    for tbl in [
        "scanned_files",
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
            INSERT INTO experience (candidate_name, job_title, company, "from", "to", details)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_name, job_title, company, "from", "to") DO UPDATE SET
                details=excluded.details
        """,
            (candidate_name, job_title, company, from_date, to_date, details_text),
        )
    self.conn.commit()

  def close(self):
    if self.conn:
      self.conn.close()
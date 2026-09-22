import hashlib
import json
import os
from typing import Any, Dict, Optional
from config import JOB_CACHE_FILE, MODEL_NAME
from llm_client import client as default_client
from openai import OpenAI
from utils import get_job_description


def generate_job_id(job_text: str) -> str:
  """Generates a short MD5 hash ID for a job description text."""
  return hashlib.md5(job_text.strip().encode("utf-8")).hexdigest()[:8]


def clear_job_cache(cache_path: str = JOB_CACHE_FILE) -> None:
  """Deletes old temporary job description save file before creating a new one."""
  if os.path.exists(cache_path):
    try:
      os.remove(cache_path)
      print(f"[+] Cleared old temporary job save file: {cache_path}")
    except Exception as e:
      print(f"[!] Failed to clear old job cache ({e}).")


def load_job_history(cache_path: str = JOB_CACHE_FILE) -> Dict[str, Any]:
  """Loads current active job description JSON from cache."""
  if os.path.exists(cache_path):
    try:
      with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception as e:
      print(f"[!] Error loading job cache ({e}).")
  return {}


def save_job_history(
    job_data: Dict[str, Any], cache_path: str = JOB_CACHE_FILE
) -> None:
  """Saves structured job details to the temporary cache file."""
  os.makedirs(os.path.dirname(cache_path), exist_ok=True)
  with open(cache_path, "w", encoding="utf-8") as f:
    json.dump(job_data, f, indent=2)


def get_or_cache_job_description(
    raw_input: str,
    client: Optional[OpenAI] = None,
    cache_path: str = JOB_CACHE_FILE,
) -> Dict[str, Any]:
  """Clears previous temporary job save, extracts structured job details via LLM,

  and saves the new target company and candidate requirement details.
  """
  llm_client = client or default_client

  raw_job_text = get_job_description(raw_input)
  job_id = generate_job_id(raw_job_text)

  # 1. Always delete old temporary save first
  clear_job_cache(cache_path)

  print(f"[+] Extracting structured details for Job ID: {job_id}...")

  prompt = f"""Extract structured target company and requirement details from this job description into JSON format.

=== JOB DESCRIPTION ===
{raw_job_text[:3500]}

=== JSON OUTPUT SCHEMA ===
{{
  "job_title": "Target Role Title",
  "company_name": "Target Company Name",
  "recipient_name": "Recruiter/Hiring Manager Name or 'Hiring Manager'",
  "recipient_title": "Recruiter Title or 'Talent Acquisition Team'",
  "required_skills": ["Skill 1", "Skill 2"],
  "required_certifications": ["Certification 1", "Certification 2"],
  "required_education": ["Degree Level / Field"],
  "required_languages": ["Language 1", "Language 2"],
  "nationality_requirements": "Nationality constraints if specified, or 'Not specified'",
  "visa_requirements": "Visa status, work permit, or sponsorship details if specified, or 'Not specified'"
}}
"""

  try:
    response = llm_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a structured data extractor. Output ONLY a valid"
                    " JSON object containing target job details."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    extracted = json.loads(response.choices[0].message.content.strip())

    job_entry = {
        "job_id": job_id,
        "job_title": extracted.get("job_title", "Position Applied For"),
        "company_name": extracted.get("company_name", "Company"),
        "recipient_name": extracted.get("recipient_name", "Hiring Manager"),
        "recipient_title": extracted.get(
            "recipient_title", "Talent Acquisition Team"
        ),
        "required_skills": extracted.get("required_skills", []),
        "required_certifications": extracted.get("required_certifications", []),
        "required_education": extracted.get("required_education", []),
        "required_languages": extracted.get("required_languages", []),
        "nationality_requirements": extracted.get(
            "nationality_requirements", "Not specified"
        ),
        "visa_requirements": extracted.get(
            "visa_requirements", "Not specified"
        ),
        "raw_text": raw_job_text,
    }

    # 2. Save fresh temporary cache
    save_job_history(job_entry, cache_path)
    print(f"[✓] Saved new target job details to temporary cache: {cache_path}")

    return job_entry

  except Exception as e:
    print(f"[!] Job extraction failed ({e}). Returning fallback structure.")
    fallback_entry = {
        "job_id": job_id,
        "job_title": "Position Applied For",
        "company_name": "Company",
        "recipient_name": "Hiring Manager",
        "recipient_title": "Talent Acquisition Team",
        "required_skills": [],
        "required_certifications": [],
        "required_education": [],
        "required_languages": [],
        "nationality_requirements": "Not specified",
        "visa_requirements": "Not specified",
        "raw_text": raw_job_text,
    }
    save_job_history(fallback_entry, cache_path)
    return fallback_entry
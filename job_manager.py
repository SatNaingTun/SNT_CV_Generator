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


def load_job_history(cache_path: str = JOB_CACHE_FILE) -> Dict[str, Any]:
  """Loads job description JSON history from cache."""
  if os.path.exists(cache_path):
    with open(cache_path, "r", encoding="utf-8") as f:
      return json.load(f)
  return {}


def save_job_history(
    history_data: Dict[str, Any], cache_path: str = JOB_CACHE_FILE
) -> None:
  """Saves job description JSON history to cache."""
  os.makedirs(os.path.dirname(cache_path), exist_ok=True)
  with open(cache_path, "w", encoding="utf-8") as f:
    json.dump(history_data, f, indent=2)


def get_or_cache_job_description(
    raw_input: str,
    client: Optional[OpenAI] = None,
    cache_path: str = JOB_CACHE_FILE,
) -> Dict[str, Any]:
  """Fetches raw job description, checks JSON cache for existing entry,

  and extracts/caches structured job details if new.
  """
  llm_client = client or default_client

  raw_job_text = get_job_description(raw_input)
  job_id = generate_job_id(raw_job_text)

  history = load_job_history(cache_path)

  if job_id in history:
    print(f"[+] Loaded job description from JSON cache (Job ID: {job_id})")
    return history[job_id]

  print(f"[+] Extracting & caching new job description (Job ID: {job_id})...")

  prompt = f"""Extract structured job details into JSON from this job description.

=== JOB DESCRIPTION ===
{raw_job_text[:3000]}

=== JSON OUTPUT SCHEMA ===
{{
  "job_title": "Target Role Title",
  "company_name": "Company Name",
  "recipient_name": "Hiring Manager Name or 'Hiring Manager'",
  "recipient_title": "Title or 'Talent Acquisition Team'",
  "required_skills": ["Skill 1", "Skill 2"]
}}
"""

  try:
    response = llm_client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "Extract structured job posting details into JSON.",
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
        "raw_text": raw_job_text,
    }

    history[job_id] = job_entry
    save_job_history(history, cache_path)
    print(f"[✓] Saved job description to cache: {cache_path}")

    return job_entry

  except Exception as e:
    print(f"[!] Job extraction failed ({e}). Returning raw description.")
    return {
        "job_id": job_id,
        "job_title": "Position Applied For",
        "company_name": "Company",
        "raw_text": raw_job_text,
    }
import glob
import json
import os
import re
from typing import List
from config import MODEL_NAME,CV_FOLDER
from latex_reader import LaTeXReader
from llm_client import client
from tqdm import tqdm
from utils import extract_text_from_file


# Safe PyLaTeX import
try:
  import pylatex
  from pylatex.utils import escape_latex

  HAS_PYLATEX = True
except ImportError:
  HAS_PYLATEX = False


def filter_tex_over_pdf(files: List[str]) -> List[str]:
  """Deduplicates files:

  1. Strips ' copy' artifacts from filenames.
  2. If both a .tex and .pdf exist for the same name, keeps ONLY the .tex file.
  """
  stem_map = {}
  for filepath in files:
    base = os.path.basename(filepath)
    stem, ext = os.path.splitext(base)
    ext = ext.lower()

    # Remove trailing ' copy' or ' copy X' created by OS file copies
    clean_stem = re.sub(
        r"\s+copy(?:\s+\d+)?$", "", stem, flags=re.IGNORECASE
    ).strip()

    if clean_stem not in stem_map:
      stem_map[clean_stem] = {}
    stem_map[clean_stem][ext] = filepath

  deduped_files = []
  for stem, ext_dict in stem_map.items():
    if ".tex" in ext_dict:
      deduped_files.append(ext_dict[".tex"])
    elif ".pdf" in ext_dict:
      deduped_files.append(ext_dict[".pdf"])

  return sorted(deduped_files)


def filter_files_by_name(
    filenames: List[str], job_description: str, max_candidates: int = 5
) -> List[str]:
  """Stage 1: Pre-screens filenames against job requirements using role alignment and tech keywords."""
  prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:1200]}

=== AVAILABLE CV FILENAMES ===
{json.dumps(filenames, indent=2)}

INSTRUCTIONS:
Select up to {max_candidates} filenames that best match the target role and domain based on filename titles (e.g., Software Engineer, System Analyst, Network, IoT).
Output STRICT JSON format:
{{"selected_filenames": ["filename1.tex", "filename2.tex"]}}
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a recruitment specialist matching CV template"
                    " names to job descriptions."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    res = json.loads(response.choices[0].message.content.strip())
    selected = res.get("selected_filenames", [])
    valid_selected = [f for f in selected if f in filenames]
    return valid_selected if valid_selected else filenames[:max_candidates]

  except Exception as e:
    print(f"\n[!] Filename screening error: {e}. Considering default set.")
    return filenames[:max_candidates]


def extract_cv_summary(filepath: str) -> dict:
  """Extracts summary and skills sections using LaTeXReader AST."""
  filename = os.path.basename(filepath)
  raw_text = ""

  try:
    raw_text = extract_text_from_file(filepath)
  except Exception as e:
    print(f"\n[!] Error reading file '{filename}': {e}")
    return {"filepath": filepath, "filename": filename, "summary": ""}

  condensed_text = ""

  if filepath.endswith(".tex"):
    try:
      reader = LaTeXReader(raw_text)
      summary = (
          reader.get_section("SUMMARY")
          or reader.get_section("PROFESSIONAL SUMMARY")
          or reader.get_section("OBJECTIVE")
      )
      skills = reader.get_section(
          "Technical Skills"
      ) or reader.get_section("SKILLS")

      if summary or skills:
        condensed_text = (
            f"Summary:\n{summary[:500]}\n\nSkills:\n{skills[:500]}"
        )
      else:
        condensed_text = raw_text[:1000]

      if HAS_PYLATEX:
        condensed_text = escape_latex(condensed_text)

    except Exception as e:
      print(
          f"\n[!] Parsing error for '{filename}': {e}. Using raw text"
          " fallback."
      )
      condensed_text = raw_text[:1000]
  else:
    condensed_text = raw_text[:1000]

  return {
      "filepath": filepath,
      "filename": filename,
      "summary": condensed_text,
  }


def score_cv_match(cv_info: dict, job_description: str) -> float:
  """Evaluates template relevance against the job posting."""
  if not cv_info.get("summary"):
    return 0.0

  prompt = f"""=== TARGET JOB DESCRIPTION ===
{job_description[:1500]}

=== CANDIDATE CV CONTENT ({cv_info['filename']}) ===
{cv_info['summary']}

INSTRUCTIONS:
Evaluate how well this CV template's target role, experience summary, and technical focus match the job description.
Score from 0 (completely irrelevant) to 100 (perfect domain & skill match).
Output STRICT JSON:
{{"score": <number_0_to_100>}}
"""
  try:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an ATS evaluator rating CV template relevance."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    res = json.loads(response.choices[0].message.content.strip())
    return float(res.get("score", 0))

  except Exception as e:
    print(f"\n[!] Scoring failed for '{cv_info['filename']}': {e}")
    return 0.0


def select_optimal_cv_file(folder_path: str, job_description: str) -> str:
  """Lists candidate templates, pre-screens and scores recommendations,

  and allows selecting any template by item number (1..N) or filename string.
  """
  raw_files = glob.glob(os.path.join(folder_path, "*.tex")) + glob.glob(
      os.path.join(folder_path, "*.pdf")
  )
  if not raw_files:
    raise FileNotFoundError(f"No .tex or .pdf CV files found in {folder_path}")

  # 1. Deduplicate files (strip ' copy' and prioritize .tex over .pdf)
  files = filter_tex_over_pdf(raw_files)

  filename_to_path = {os.path.basename(f): f for f in files}
  all_filenames = sorted(list(filename_to_path.keys()))

  # 2. Display full numbered candidate file list
  print(
      f"\n[+] Found {len(all_filenames)} candidate CV template file(s)"
      " (showing .tex where .pdf duplicates exist):"
  )
  for idx, fname in enumerate(all_filenames, 1):
    print(f"  {idx:2d}. {fname}")
  print()

  # 3. Stage 1: Filename Pre-screening
  if len(all_filenames) > 4:
    print("[1/2] Pre-screening filenames against job description...")
    candidate_filenames = filter_files_by_name(
        all_filenames, job_description, max_candidates=5
    )
  else:
    candidate_filenames = all_filenames

  candidate_paths = [filename_to_path[fname] for fname in candidate_filenames]

  # 4. Stage 2: Evaluation & Scoring
  print("\n[2/2] Evaluating template relevance scores:")
  scored_results = []

  for filepath in tqdm(candidate_paths, desc="Scoring Templates", unit="file"):
    summary_info = extract_cv_summary(filepath)
    score = score_cv_match(summary_info, job_description)
    scored_results.append((summary_info["filename"], filepath, score))

  scored_results.sort(key=lambda x: x[2], reverse=True)

  # 5. Display Shortlisted Recommendations
  print("\n" + "=" * 60)
  print("   SHORTLISTED CV TEMPLATES & MATCH SCORES")
  print("=" * 60)
  for idx, (filename, fpath, score) in enumerate(scored_results, 1):
    indicator = " (Top Recommendation)" if idx == 1 else ""
    print(f" [{idx}] {filename:<38} | Score: {score}/100{indicator}")
  print("=" * 60)

  top_choice_file = scored_results[0][1]
  top_choice_name = scored_results[0][0]

  # 6. Interactive Selection Prompt
  print(f"\nDefault selected template: [{top_choice_name}]")
  user_choice = input(
      f"Press [ENTER] to use top recommendation, or enter file number (1-"
      f"{len(all_filenames)}) / filename to override: "
  ).strip()

  if not user_choice:
    print(f"[✓] Confirmed template: {top_choice_name}")
    return top_choice_file

  # Resolution Step 1: Match entered number against main enumerated file list (1..N)
  if user_choice.isdigit():
    choice_num = int(user_choice)
    if 1 <= choice_num <= len(all_filenames):
      selected_fname = all_filenames[choice_num - 1]
      selected_path = filename_to_path[selected_fname]
      print(f"[✓] User selected [{choice_num}]: {selected_fname}")
      return selected_path

  # Resolution Step 2: Match exact filename
  if user_choice in filename_to_path:
    print(f"[✓] User selected: {user_choice}")
    return filename_to_path[user_choice]

  # Resolution Step 3: Match partial filename
  for fname, fpath in filename_to_path.items():
    if user_choice.lower() in fname.lower():
      print(f"[✓] Matched user choice to: {fname}")
      return fpath

  print(
      "[!] Input choice unrecognized. Defaulting to top recommendation:"
      f" {top_choice_name}"
  )
  return top_choice_file

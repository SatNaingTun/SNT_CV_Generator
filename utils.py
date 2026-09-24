import os
import shutil
import subprocess
import sys
from bs4 import BeautifulSoup
import requests
from TexSoup import TexSoup

from config import IGNORE_FOLDERS, IMAGE_EXTENSIONS
from latex_reader import LaTeXReader
# from latex_cv_writer import LaTeXCVWriter
import os
import os

try:
  import pymupdf  # Recommended modern import
  HAS_PYMUPDF = True
except ImportError:
  HAS_PYMUPDF = False

try:
  import pypdf
  HAS_PYPDF = True
except ImportError:
  HAS_PYPDF = False


def extract_text_from_file(filepath: str) -> str:
  """Extracts text from files (.tex, .pdf, .txt) extremely fast.

  Uses PyMuPDF for PDFs if available, falling back to pypdf.
  """
  ext = os.path.splitext(filepath)[1].lower()
  text = ""

  if ext in [".tex", ".txt"]:
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
      return f.read()

  elif ext == ".pdf":
    # 1. Try PyMuPDF first (blazing fast C-bound extraction)
    if HAS_PYMUPDF:
      try:
        with pymupdf.open(filepath) as doc:
          text = "".join(page.get_text() for page in doc)
        if text.strip():
          return text
      except Exception:
        pass

    # 2. Fallback to pypdf if PyMuPDF fails
    if HAS_PYPDF:
      try:
        reader = pypdf.PdfReader(filepath)
        text = "".join(page.extract_text() or "" for page in reader.pages)
        return text
      except Exception:
        pass

  return text


def format_job_summary(job_data: dict) -> str:
  """Formats structured job details into a clean summary string for LLM prompts."""
  skills = ", ".join(job_data.get("required_skills", []))
  certs = ", ".join(job_data.get("required_certifications", []))
  edu = ", ".join(job_data.get("required_education", []))
  langs = ", ".join(job_data.get("required_languages", []))

  return f"""TARGET ROLE: {job_data.get('job_title', 'N/A')}
COMPANY: {job_data.get('company_name', 'N/A')}
RECRUITER/CONTACT: {job_data.get('recipient_name', 'Hiring Manager')} ({job_data.get('recipient_title', 'Talent Acquisition')})
REQUIRED SKILLS: {skills if skills else 'N/A'}
REQUIRED CERTIFICATIONS: {certs if certs else 'N/A'}
REQUIRED EDUCATION: {edu if edu else 'N/A'}
REQUIRED LANGUAGES: {langs if langs else 'N/A'}
NATIONALITY REQUIREMENTS: {job_data.get('nationality_requirements', 'Not specified')}
VISA REQUIREMENTS: {job_data.get('visa_requirements', 'Not specified')}"""


def read_text_file(filepath: str) -> str:
  """Reads plain text content from a local file safely."""
  if not os.path.exists(filepath):
    raise FileNotFoundError(f"File not found: {filepath}")
  with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
    return f.read().strip()


def write_text_file(filepath: str, content: str) -> None:
  """Writes text content to a file, ensuring parent directories exist."""
  os.makedirs(os.path.dirname(filepath), exist_ok=True)
  with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)




def copy_cv_assets(
    cv_folder: str, output_dir: str, ignore_folders: list = None
):
  """Copies image files and subdirectories to output directory."""
  if ignore_folders is None:
    ignore_folders = IGNORE_FOLDERS

  print(f"[+] Copying image assets from {cv_folder} to {output_dir}...")
  for item in os.listdir(cv_folder):
    if item in ignore_folders:
      continue

    src_path = os.path.join(cv_folder, item)
    dst_path = os.path.join(output_dir, item)
    ext = os.path.splitext(item)[1].lower()

    if os.path.isdir(src_path):
      if os.path.exists(dst_path):
        shutil.rmtree(dst_path)
      shutil.copytree(
          src_path,
          dst_path,
          ignore=shutil.ignore_patterns(*ignore_folders, "*.pyc"),
      )
    elif os.path.isfile(src_path) and ext in IMAGE_EXTENSIONS:
      os.makedirs(output_dir, exist_ok=True)
      shutil.copy2(src_path, dst_path)




def strip_straggling_pagebreaks(tex_content: str) -> str:
  """Uses TexSoup AST parsing to detect \\newpage breaks.

  If the section following \\newpage is <= 4 lines (1-3 lines), removes the
  break.
  """
  try:
    soup = TexSoup(tex_content)
    pagebreaks = list(soup.find_all("newpage"))

    for pb in pagebreaks:
      following_text = str(pb.next_sibling) if pb.next_sibling else ""
      lines = [l.strip() for l in following_text.split("\n") if l.strip()]

      if len(lines) <= 4:
        pb.delete()
        print(
            "[+] Removed straggling \\newpage command (section <= 4 lines)."
        )

    return str(soup)
  except Exception as e:
    print(f"[!] AST pagebreak cleanup warning: {e}")
    return tex_content


def compile_latex_to_pdf(tex_filepath: str, output_dir: str) -> str:
  """Compiles a generated .tex file to PDF using pdflatex."""
  filename = os.path.basename(tex_filepath)
  file_stem = os.path.splitext(filename)[0]
  expected_pdf = os.path.abspath(os.path.join(output_dir, f"{file_stem}.pdf"))

  print(f"[+] Compiling {filename} to PDF with pdflatex...")
  try:
    subprocess.run(
        [
            "pdflatex",
            f"-output-directory={output_dir}",
            "-interaction=nonstopmode",
            tex_filepath,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"[✓] Successfully compiled PDF: {expected_pdf}")
    return expected_pdf
  except (subprocess.CalledProcessError, FileNotFoundError) as e:
    print(f"[!] pdflatex compilation failed for {filename}: {e}")
    return ""


def get_job_description(input_str: str) -> str:
  """Fetches job posting text from a URL, local file path, or raw text."""
  clean_input = input_str.strip()

  if os.path.isfile(clean_input):
    print(f"[+] Reading job description from file: {clean_input}")
    return read_text_file(clean_input)

  if clean_input.startswith("http://") or clean_input.startswith("https://"):
    print(f"[+] Scraping job URL: {clean_input}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    response = requests.get(clean_input, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    for script in soup(["script", "style", "nav", "footer"]):
      script.decompose()
    return soup.get_text(separator=" ", strip=True)

  return clean_input


def prompt_for_job_description() -> str:
  """Prompts the user for a job description via raw multi-line text, file path, or URL.

  Press Ctrl+D (Linux/macOS) or Ctrl+Z then Enter (Windows) when finished.
  """
  print("\n" + "=" * 60)
  print("      CV TAILORING PIPELINE - JOB DESCRIPTION INPUT")
  print("=" * 60)
  print("You can provide:")
  print("  1. A file path (e.g., job_desc.txt)")
  print("  2. A job posting URL (e.g., https://...)")
  print("  3. Direct multi-line pasted text")
  print("-" * 60)
  print(
      "Paste your input below. When finished, press Ctrl+D (Linux/Mac) or"
      " Ctrl+Z + Enter (Windows):"
  )
  print("-" * 60)

  try:
    raw_input = sys.stdin.read().strip()
  except KeyboardInterrupt:
    print("\n[!] Operation cancelled by user.")
    sys.exit(0)

  if not raw_input:
    print("\n[!] Empty input received. Using default fallback job description.")
    return """
        We are looking for an IT Systems Administrator / Software Engineer to support, maintain, and 
        enhance core IT infrastructure, SQL databases, and C# internal reporting software. 
        Experience with Linux servers, AWS, network troubleshooting, and Python automation is required.
        """

  if "\n" not in raw_input:
    return get_job_description(raw_input)

  return raw_input
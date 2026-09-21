# Local LLM LaTeX CV Tailor

An automated Python pipeline designed to customize LaTeX resumes and CVs to specific job descriptions using a lightweight local LLM (e.g., Gemma 3 1B via `llama.cpp`).

Unlike whole-document prompt approaches that frequently drop section titles or metadata, this tool processes experience entries **company-by-company**, keeping company names, job titles, and date ranges frozen in Python while rephrasing itemized bullet points to align with target job requirements.

---

## Prerequisites

* **Python:** 3.8+
* **LaTeX Engine:** TeX Live / MiKTeX (`pdflatex` available in system `PATH`)
* **Local Inference Backend:** `llama.cpp`

---

## Setup & Quick Start

### 1. Install `llama.cpp` & Download Model

For detailed building and installation instructions across Linux, macOS, and Windows, refer to the official [llama.cpp README](https://github.com/ggml-org/llama.cpp/blob/master/README.md).

Once `llama.cpp` is built, create a `models/` folder and download the quantized GGUF model:


```
cd llama.cpp
mkdir -p models
wget -O models/gemma-3-1b-it.gguf \
  [https://huggingface.co/bartowski/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf](https://huggingface.co/bartowski/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf)

```

### 2. Launch llama-server
Start the local API server backend using llama.cpp:

```
./llama-server \
  -m models/gemma-3-1b-it.gguf \
  --port 8013 \
  -c 4096 \
  -ngl 99 \
  --host 127.0.0.1

```

### 3. Clone Repository & Set Up Python Environment
Clone the repository and set up a Python virtual environment:


```
# Clone the repository
git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
cd your-repo-name

# Create virtual environment
python3 -m venv venv

```


Activate Virtual Environment:

Linux / macOS:

Bash
```
source venv/bin/activate

```
Windows (Command Prompt):

DOS
```
venv\Scripts\activate.bat

```
Windows (PowerShell):

PowerShell
```
.\venv\Scripts\Activate.ps1

```

4. Install Dependencies & Run
Install the Python requirements and launch the pipeline:

Bash
```
# Install required packages
pip install -r requirements.txt

# Run the generator script
python generate_cv.py

```
Paste the target job description text, local text file path, or job posting URL, then press [ENTER] followed by [Ctrl+D] (or enter an empty line) to start the tailoring process.

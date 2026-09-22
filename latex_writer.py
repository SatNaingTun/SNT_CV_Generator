import re


class LaTeXWriter:
  """Escapes and formats structured content into valid LaTeX code."""

  @staticmethod
  def escape_latex_chars(text: str) -> str:
    """Escapes special LaTeX characters while preserving existing commands."""
    if not text:
      return ""

    # Protect existing commands using non-special tokens (no underscores)
    text = text.replace(r"\%", "XXPERCENTESCXX")
    text = text.replace(r"\&", "XXAMPESCXX")
    text = text.replace(r"\#", "XXHASHESCXX")
    text = text.replace(r"\_", "XXUNDERSCOREESCXX")

    # Escape raw unescaped characters
    text = text.replace("%", r"\%")
    text = text.replace("&", r"\&")
    text = text.replace("#", r"\#")
    text = text.replace("_", r"\_")

    # Restore protected commands
    text = text.replace("XXPERCENTESCXX", r"\%")
    text = text.replace("XXAMPESCXX", r"\&")
    text = text.replace("XXHASHESCXX", r"\#")
    text = text.replace("XXUNDERSCOREESCXX", r"\_")

    return text

  @staticmethod
  def write_skills_as_list(skills_dict: dict[str, str]) -> str:
    """Converts any dictionary of skills into a clean, compile-safe LaTeX itemize environment."""
    if not skills_dict:
      return ""

    lines = ["\\begin{itemize}"]
    for category, skills_str in skills_dict.items():
      cat_clean = LaTeXWriter.escape_latex_chars(
          category.strip().rstrip(":")
      )
      val_clean = LaTeXWriter.escape_latex_chars(skills_str.strip())
      lines.append(f"    \\item \\textbf{{{cat_clean}:}} {val_clean}")
    lines.append("\\end{itemize}")

    return "\n".join(lines)

  @staticmethod
  def write_sentence(text: str) -> str:
    """Sanitizes plain prose text for safe insertion into LaTeX."""
    return LaTeXWriter.escape_latex_chars(text.strip())
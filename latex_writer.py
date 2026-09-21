import re


class LaTeXWriter:
  """Escapes and formats structured content into valid LaTeX code."""

  @staticmethod
  def escape_latex_chars(text: str) -> str:
    """Escapes special LaTeX characters while preserving existing commands."""
    if not text:
      return ""

    # Protect existing commands
    text = text.replace(r"\%", "__PERCENT_ESC__")
    text = text.replace(r"\&", "__AMP_ESC__")
    text = text.replace(r"\#", "__HASH_ESC__")
    text = text.replace(r"\_", "__UNDERSCORE_ESC__")

    # Escape raw unescaped characters
    text = text.replace("%", r"\%")
    text = text.replace("&", r"\&")
    text = text.replace("#", r"\#")
    text = text.replace("_", r"\_")

    # Restore protected commands
    text = text.replace("__PERCENT_ESC__", r"\%")
    text = text.replace("__AMP_ESC__", r"\&")
    text = text.replace("__HASH_ESC__", r"\#")
    text = text.replace("__UNDERSCORE_ESC__", r"\_")

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
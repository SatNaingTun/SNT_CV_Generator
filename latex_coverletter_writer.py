class LaTeXCoverLetterWriter:
    @staticmethod
    def write_sentence(text: str) -> str:
        """Escapes special characters for normal text, handling C# simply and cleanly."""
        if not text:
            return ""
        
        safe_text = (
            text.replace("&", "\\&")
            .replace("%", "\\%")
            .replace("$", "\\$")
            .replace("_", "\\_")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("—", "--")
        )
        return safe_text.replace("C#", "C\\#").replace("c#", "c\\#")

    @staticmethod
    def extract_header_block(name: str, contact_info: dict, target_position: str = "") -> str:
        """Generates the professional contact header block omitting location and replacing email with target position."""
        phone = contact_info.get("phone", "")
        linkedin = contact_info.get("linkedin", "")
        github = contact_info.get("github", "")

        contact_parts = []
        if target_position:
            contact_parts.append(f"\\textbf{{Position:}} {target_position}")
        if phone:
            contact_parts.append(phone)
        if linkedin:
            display_li = linkedin.replace("https://", "").replace("http://", "")
            contact_parts.append(f"\\href{{{linkedin}}}{{{display_li}}}")
        if github:
            display_gh = github.replace("https://", "").replace("http://", "")
            contact_parts.append(f"\\href{{{github}}}{{{display_gh}}}")

        contact_str = " \\textbar{} ".join(contact_parts)

        return f"""{{\\Large \\textbf{{{name}}}}}\\\\[4pt]
{contact_str}"""

    @staticmethod
    def build_full_document(header_str: str, body_1_para: str, body_2_para: str, body_3_para: str, sender_name: str) -> str:
        """Assembles the complete LaTeX document using your exact preferred layout template."""
        p1 = LaTeXCoverLetterWriter.write_sentence(body_1_para)
        p2 = LaTeXCoverLetterWriter.write_sentence(body_2_para)
        p3 = LaTeXCoverLetterWriter.write_sentence(body_3_para)

        return f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[margin=0.75in]{{geometry}}
\\usepackage{{hyperref}}
\\usepackage{{parskip}}

\\hypersetup{{
    colorlinks=true,
    linkcolor=blue,
    urlcolor=blue
}}

\\begin{{document}}

\\pagestyle{{empty}}

% Header Block
{header_str}

\\vspace{{1.2em}}

\\today

\\vspace{{1em}}

Dear Hiring Manager,

\\vspace{{0.5em}}

{p1}

\\vspace{{0.8em}}

{p2}

\\vspace{{0.8em}}

{p3}

\\vspace{{1.5em}}

Sincerely,

\\vspace{{1.5em}}

{sender_name}

\\end{{document}}
"""
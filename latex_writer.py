class LaTeXWriter:
    @staticmethod
    @staticmethod
    @staticmethod
    def write_sentence(text: str) -> str:
        """Escapes special characters for normal text, handling C# simply and cleanly."""
        if not text:
            return ""
        
        # Perform standard escapes (excluding backslash and hash to keep it simple)
        safe_text = (
            text.replace("&", "\\&")
            .replace("%", "\\%")
            .replace("$", "\\$")
            .replace("_", "\\_")
            .replace("{", "\\{")
            .replace("}", "\\}")
            .replace("—", "--")
        )
        
        # Directly map C# to proper LaTeX C\#
        return safe_text.replace("C#", "C\\#").replace("c#", "c\\#")
    @staticmethod
    def write_list(items: list) -> str:
        """Formats a list of strings into LaTeX itemize environment."""
        if not items:
            return ""
        out = ["\\begin{itemize}"]
        for item in items:
            out.append(f"  \\item {LaTeXWriter.write_sentence(item)}")
        out.append("\\end{itemize}")
        return "\n".join(out)

    @staticmethod
    def initialize_document_from_template(raw_tex: str, format_type: str = "snt") -> str:
        """Initializes document layout based on chosen format (ATS vs SNT)."""
        if format_type.lower() == "ats":
            return """\\documentclass[10pt,a4paper]{article}
\\usepackage[top=2cm,bottom=2cm,left=2cm,right=2cm]{geometry}
\\usepackage{titlesec, enumitem, hyperref}
\\setlength{\\parindent}{0pt}
\\setlist[itemize]{leftmargin=*, noitemsep, topsep=2pt}
\\titleformat{\\section}{\\large\\bfseries}{}{0em}{[\\titlerule]}
\\begin{document}
\\sloppy"""
        else:
            doc_idx = raw_tex.find("\\begin{document}")
            if doc_idx != -1:
                preamble = raw_tex[:doc_idx + len("\\begin{document}")]
                return preamble + "\n\n\\sloppy\n"
        
        return """\\documentclass[10pt,a4paper]{article}
\\usepackage[top=2cm,bottom=2cm,left=2cm,right=2cm]{geometry}
\\usepackage{titlesec, enumitem, hyperref}
\\setlength{\\parindent}{0pt}
\\begin{document}
\\sloppy"""

    @staticmethod
    def extract_header_block(name: str, contact_info) -> str:
        if isinstance(contact_info, dict):
            email = contact_info.get("email", "")
            phone = contact_info.get("phone", "")
            linkedin = contact_info.get("linkedin", "")
            github = contact_info.get("github", "")

            contact_parts = []
            if email:
                contact_parts.append(f"\\href{{mailto:{email}}}{{{email}}}")
            if phone:
                contact_parts.append(phone)
            if linkedin:
                display_li = linkedin.replace("https://", "").replace("http://", "")
                contact_parts.append(f"\\href{{{linkedin}}}{{{display_li}}}")
            if github:
                display_gh = github.replace("https://", "").replace("http://", "")
                contact_parts.append(f"\\href{{{github}}}{{{display_gh}}}")

            contact_str = " | ".join(contact_parts)
        else:
            contact_str = str(contact_info) if contact_info else ""

        return f"""\\begin{{center}}
\\begin{{minipage}}{{0.73\\textwidth}}
\\centering
{{\\Huge \\textbf{{{name}}}}}\\\\[6pt]

{contact_str}
\\end{{minipage}}
\\end{{center}}
%------------------------"""

    @staticmethod
    def write_summary_section(summary: str) -> str:
        cleaned_summary = LaTeXWriter.write_sentence(summary)
        return f"\\section*{{Professional Summary}}\n\n{cleaned_summary}\n"

    @staticmethod
    def write_skills_section(skills: dict) -> str:
        out = ["\\section{Technical Skills}\n", "\\begin{itemize}"]
        for cat, items in skills.items():
            safe_cat = LaTeXWriter.write_sentence(cat)
            if isinstance(items, list):
                safe_items = ", ".join([LaTeXWriter.write_sentence(i) for i in items])
            else:
                safe_items = LaTeXWriter.write_sentence(str(items))
            out.append(f"    \\item \\textbf{{{safe_cat}:}} {safe_items}")
        out.append("\\end{itemize}\n")
        return "\n".join(out)

    @staticmethod
    def write_core_competencies_section(competencies: list) -> str:
        if not competencies:
            return ""
        out = ["\\section*{Core Competencies}\n", "\\begin{itemize}[leftmargin=*]"]
        for comp in competencies:
            out.append(f"\\item {LaTeXWriter.write_sentence(comp)}")
        out.append("\\end{itemize}\n")
        return "\n".join(out)

    @staticmethod
    def write_education_section(education: list) -> str:
        out = ["\\section*{Education}\n"]
        for idx, e in enumerate(education):
            deg = LaTeXWriter.write_sentence(e.get('degree', ''))
            inst = LaTeXWriter.write_sentence(e.get('institution', ''))
            f_date = LaTeXWriter.write_sentence(e.get('from', ''))
            t_date = LaTeXWriter.write_sentence(e.get('to', ''))
            coursework = e.get('coursework', [])
            thesis = LaTeXWriter.write_sentence(e.get('thesis', ''))

            out.append(f"\\textbf{{{deg}}} \\hfill {f_date} -- {t_date} \\\\")
            out.append(inst)
            if coursework or thesis:
                out.append("\\begin{itemize}")
                if coursework:
                    cw_list = [LaTeXWriter.write_sentence(cw) for cw in coursework] if isinstance(coursework, list) else [LaTeXWriter.write_sentence(coursework)]
                    cw_str = ", ".join(cw_list)
                    out.append(f"    \\item \\textbf{{Relevant Coursework & Subjects}}: {cw_str}")
                if thesis:
                    out.append(f"    \\item \\textbf{{Thesis / Research Focus:}} {thesis}")
                out.append("\\end{itemize}")
            if idx < len(education) - 1:
                out.append("\\vspace{4mm}\n")
        return "\n".join(out)

    @staticmethod
    def write_experience_section(experiences: list) -> str:
        out = ["\\newpage", "\\section*{PROFESSIONAL EXPERIENCE}\n"]
        for idx, exp in enumerate(experiences):
            title = LaTeXWriter.write_sentence(exp.get('job_title') or exp.get('title', ''))
            company = LaTeXWriter.write_sentence(exp.get('company', ''))
            from_d = LaTeXWriter.write_sentence(exp.get('from', ''))
            to_d = LaTeXWriter.write_sentence(exp.get('to', ''))
            bullets = exp.get('bullet_points', [])
            
            out.append(f"\\textbf{{{title}}} \\hfill {from_d} -- {to_d} \\\\")
            out.append(company)
            out.append("")
            out.append("\\begin{itemize}")
            for b in bullets:
                out.append(f"    \\item {LaTeXWriter.write_sentence(b)}")
            out.append("\\end{itemize}")
            if idx < len(experiences) - 1:
                out.append("\\vspace{4mm}\n")
        return "\n".join(out)

    @staticmethod
    def write_projects_section(projects: list) -> str:
        out = ["\\section*{Selected Projects}\n"]
        for idx, p in enumerate(projects):
            p_name = LaTeXWriter.write_sentence(p.get('project_name', ''))
            details = p.get('details', [])
            
            out.append(f"\\textbf{{{p_name}}}")
            out.append("")
            out.append("\\begin{itemize}")
            for d in details:
                out.append(f"\\item {LaTeXWriter.write_sentence(d)}")
            out.append("\\end{itemize}")
            if idx < len(projects) - 1:
                out.append("\\vspace{4mm}\n")
        return "\n".join(out)

    @staticmethod
    def write_certifications_section(certs: list) -> str:
        out = ["\\section{Certifications}\n", "\\begin{itemize}"]
        for c in certs:
            name = LaTeXWriter.write_sentence(c.get('certificate_name', ''))
            org = LaTeXWriter.write_sentence(c.get('issuing_organization', ''))
            year = LaTeXWriter.write_sentence(c.get('from', ''))
            org_str = f" --- {org}" if org else ""
            year_str = f" ({year})" if year else ""
            out.append(f"\\item {name}{org_str}{year_str}")
        out.append("\\end{itemize}\n")
        return "\n".join(out)

    @staticmethod
    def write_languages_section(languages: list) -> str:
        safe_langs = [LaTeXWriter.write_sentence(l) for l in languages]
        lang_str = " \\\\ \n".join(safe_langs)
        return f"\\section*{{LANGUAGES}}\n{lang_str}\n"

    @staticmethod
    def write_summary_section(summary: str) -> str:
        cleaned_summary = LaTeXWriter.write_sentence(summary)
        return f"\\section*{{Professional Summary}}\n\n{cleaned_summary}\n"
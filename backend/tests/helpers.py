import io
import zipfile


def make_pdf(text: str) -> bytes:
    """Minimal valid single-page text PDF (for tests only)."""
    lines = text.split("\n")
    stream = "BT /F1 11 Tf 14 TL 50 750 Td " + " ".join(f"({l.replace('(', '[').replace(')', ']')}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def make_docx(paragraphs, extra_files=None) -> bytes:
    import docx
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    if extra_files:
        zin = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, zin.read(item.filename))
            for name, data in extra_files.items():
                zout.writestr(name, data)
        return out.getvalue()
    return buf.getvalue()


SAMPLE_CV = """Jane Example
jane@example.com   082 123 4567

PROFILE
Graphic designer with Adobe Photoshop and Illustrator skills.

WORK EXPERIENCE
Junior Designer, Studio X   Jan 2021 - Present
- Created social media graphics and increased engagement by 35%
Intern, Agency Y   Feb 2020 - Dec 2020
- Designed layouts in Figma for 12 clients

EDUCATION
National Diploma in Graphic Design, 2019

SKILLS
Photoshop, Illustrator, Social media, Figma

LANGUAGES
English, isiZulu
"""

import os
from docx import Document

def parse_resume(file_path: str) -> str:
    """
    Extracts text from a resume file (PDF or DOCX).
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _extract_from_pdf(file_path)
    elif ext == ".docx":
        return _extract_from_docx(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

def _extract_from_pdf(file_path: str) -> str:
    import pdfplumber

    text = ""
    # Read up to 6 pages — 3 was too tight and cut off late sections such as
    # "Certifications & Achievements" on some 2-3 page resumes where the
    # section spills onto page 4 in exports.
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages[:6]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    return text.strip()

def _extract_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text.strip()

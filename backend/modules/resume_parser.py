import os
import pdfplumber
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
    text = ""
    with pdfplumber.open(file_path) as pdf:
        # Limit to first 3 pages for maximum speed
        for page in pdf.pages[:3]:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    return text.strip()

def _extract_from_docx(file_path: str) -> str:
    doc = Document(file_path)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text.strip()

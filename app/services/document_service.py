import re
from pypdf import PdfReader


def extract_text_from_pdf(path: str) -> str:
    reader = PdfReader(path)
    parts: list[str] = []

    for page in reader.pages:
        txt = page.extract_text() or ""
        txt = txt.strip()
        if txt:
            parts.append(txt)

    return "\n\n".join(parts)


def extract_text_from_pptx(path: str) -> str:
    from pptx import Presentation  # type: ignore

    prs = Presentation(path)
    parts: list[str] = []

    for slide in prs.slides:
        slide_texts: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = " ".join(run.text for run in para.runs).strip()
                    if line:
                        slide_texts.append(line)
        if slide_texts:
            parts.append("\n".join(slide_texts))

    return "\n\n".join(parts)


def extract_text_from_docx(path: str) -> str:
    from docx import Document as DocxDocument  # type: ignore

    doc = DocxDocument(path)
    parts = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
    return "\n\n".join(parts)


def extract_text(path: str, content_type: str) -> str:
    """Despacha para o extrator correto com base no content_type."""
    if content_type == "application/pdf":
        return extract_text_from_pdf(path)
    if content_type in (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint",
    ):
        return extract_text_from_pptx(path)
    if content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return extract_text_from_docx(path)
    raise ValueError(f"Tipo de arquivo não suportado: {content_type}")


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """
    MVP: chunking por caracteres com overlap.
    Depois, se quiser, dá para migrar para chunking por tokens.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    n = len(cleaned)

    while start < n:
        end = min(start + max_chars, n)

        # tenta cortar em um ponto final próximo do final do chunk
        cut = cleaned.rfind(".", start, end)
        if cut == -1 or cut < start + int(max_chars * 0.5):
            cut = end
        else:
            cut = cut + 1  # inclui o ponto

        chunk = cleaned[start:cut].strip()
        if chunk:
            chunks.append(chunk)

        next_start = cut - overlap
        if next_start <= start:
            next_start = cut  # garante progresso
        start = next_start

    return chunks

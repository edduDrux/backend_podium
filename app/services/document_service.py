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

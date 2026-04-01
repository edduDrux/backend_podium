"""
Testes de extração de texto — PPTX e DOCX criados programaticamente.
"""
from pathlib import Path

import pytest

from app.services.document_service import extract_text, chunk_text


# ---------------------------------------------------------------------------
# Fixtures — criam arquivos mínimos em memória
# ---------------------------------------------------------------------------


@pytest.fixture
def pptx_file(tmp_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    layout = prs.slide_layouts[5]  # blank slide

    slide1 = prs.slides.add_slide(layout)
    txBox = slide1.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    txBox.text_frame.text = "Título do primeiro slide"
    p = txBox.text_frame.add_paragraph()
    p.text = "Conteúdo detalhado do slide um"

    slide2 = prs.slides.add_slide(layout)
    txBox2 = slide2.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    txBox2.text_frame.text = "Segundo slide com dados"

    path = tmp_path / "apresentacao.pptx"
    prs.save(str(path))
    return path


@pytest.fixture
def docx_file(tmp_path: Path) -> Path:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_paragraph("Introdução do documento")
    doc.add_paragraph("Segundo parágrafo com mais detalhes")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Célula A1"
    table.cell(0, 1).text = "Célula B1"
    table.cell(1, 0).text = "Célula A2"
    table.cell(1, 1).text = "Célula B2"

    doc.add_paragraph("Conclusão após a tabela")

    path = tmp_path / "documento.docx"
    doc.save(str(path))
    return path


@pytest.fixture
def docx_no_tables(tmp_path: Path) -> Path:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    doc.add_paragraph("Apenas texto simples")
    doc.add_paragraph("Sem tabelas neste documento")

    path = tmp_path / "simples.docx"
    doc.save(str(path))
    return path


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------


def test_extract_pptx_all_slides(pptx_file: Path):
    """Extrai texto de todos os slides, separados por \\n\\n."""
    text = extract_text(str(pptx_file), "application/vnd.openxmlformats-officedocument.presentationml.presentation")

    assert "Título do primeiro slide" in text
    assert "Conteúdo detalhado do slide um" in text
    assert "Segundo slide com dados" in text
    # Slides separados por \n\n
    assert "\n\n" in text


def test_extract_pptx_by_suffix(pptx_file: Path):
    """Routing por sufixo .pptx funciona mesmo com content_type genérico."""
    text = extract_text(str(pptx_file), "application/octet-stream")

    assert "Título do primeiro slide" in text
    assert "Segundo slide com dados" in text


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def test_extract_docx_paragraphs(docx_file: Path):
    """Extrai texto de todos os parágrafos."""
    text = extract_text(str(docx_file), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    assert "Introdução do documento" in text
    assert "Segundo parágrafo com mais detalhes" in text
    assert "Conclusão após a tabela" in text


def test_extract_docx_includes_tables(docx_file: Path):
    """Texto de tabelas é incluído na extração."""
    text = extract_text(str(docx_file), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    assert "Célula A1" in text
    assert "Célula B1" in text
    assert "Célula A2" in text
    assert "Célula B2" in text


def test_extract_docx_by_suffix(docx_file: Path):
    """Routing por sufixo .docx funciona mesmo com content_type genérico."""
    text = extract_text(str(docx_file), "application/octet-stream")

    assert "Introdução do documento" in text


def test_extract_docx_without_tables(docx_no_tables: Path):
    """DOCX sem tabelas extrai apenas parágrafos sem erro."""
    text = extract_text(str(docx_no_tables), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    assert "Apenas texto simples" in text
    assert "Sem tabelas neste documento" in text


# ---------------------------------------------------------------------------
# Erros e edge cases
# ---------------------------------------------------------------------------


def test_extract_unsupported_extension_raises():
    """Extensão não suportada deve levantar ValueError."""
    with pytest.raises(ValueError, match="não suportado"):
        extract_text("/fake/arquivo.xyz", "application/octet-stream")


def test_chunk_text_empty():
    """Texto vazio retorna lista vazia."""
    assert chunk_text("") == []
    assert chunk_text("   ") == []

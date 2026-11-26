from io import BytesIO
from zipfile import ZipFile

from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader

from api import docx_render
from api.server import server


def test_downloaded_letters_preserve_the_postal_address_without_a_converter(monkeypatch):
    monkeypatch.setattr(docx_render, "docx_to_pdf", lambda _: None)
    recipient = ["Sozialamt Musterstadt", "Postfach 12345", "12345 Musterstadt"]
    letter = {
        "template": "letter",
        "sender": ["Alex Muster"],
        "recipient": recipient,
        "date": "18.11.2026",
        "subject": "Übersetzungskosten",
        "body": "Ich beantrage die Erstattung.",
    }
    with TestClient(server) as client:
        docx = client.post("/chamfer/letter", json={**letter, "format": "docx"})
        pdf = client.post("/chamfer/letter", json={**letter, "format": "pdf"})
    assert docx.status_code == pdf.status_code == 200
    assert 'filename="chamfer-letter.docx"' in docx.headers["content-disposition"]
    assert 'filename="chamfer-letter.pdf"' in pdf.headers["content-disposition"]
    with ZipFile(BytesIO(docx.content)) as parts:
        embedded = [name for name in parts.namelist() if name.startswith("word/fonts/")]
        assert embedded and all(name.startswith("word/fonts/Inter") for name in embedded)
        assert b"Chamfer" in b"".join(parts.read(name) for name in parts.namelist()
                                      if name.startswith("word/footer") and name.endswith(".xml"))
    word = Document(BytesIO(docx.content))
    word_text = " ".join(word.element.body.itertext())
    pdf_text = " ".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    for line in [*recipient, letter["subject"], letter["body"]]:
        assert line in word_text
        assert line in pdf_text


def test_retired_public_api_routes_are_absent():
    with TestClient(server) as client:
        for path in ("/v1", "/v1/health", "/v1/docs", "/amtsgraph/", "/amtsgraph/health", "/lex/docs"):
            assert client.get(path, follow_redirects=False).status_code == 404, path
        for path in ("/pdf/letter", "/v1/pdf/letter"):
            assert client.post(path, json={}, follow_redirects=False).status_code == 404, path

"""Discover, load and clean text from the PDF knowledge-base documents."""
import re
from pathlib import Path
import pypdf
import config


def discover_documents():
    """Return list of PDF filenames present in both the knowledge base folder
    AND the document registry (config.py). Files not in the registry are
    skipped with a warning, since every source must be explicitly classified."""
    found = []
    for f in sorted(config.KNOWLEDGE_BASE_DIR.glob("*.pdf")):
        if f.name not in config.DOCUMENT_REGISTRY:
            print(f"[WARN] {f.name} is not in DOCUMENT_REGISTRY - skipping (unclassified source).")
            continue
        found.append(f)
    return found


def clean_text(text: str) -> str:
    """Normalize whitespace/newlines produced by pypdf extraction."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return text.strip()


def load_document_pages(path: Path):
    """Return list of (page_number, cleaned_text) for a PDF."""
    reader = pypdf.PdfReader(str(path))
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        pages.append((i, clean_text(raw)))
    return pages

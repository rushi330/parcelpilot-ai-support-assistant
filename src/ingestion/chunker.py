"""Chunking strategy: prefer splitting on numbered section headings (e.g.
"1. Support terms", "2. Cancellation terms") since every source document in
this data pack uses that structure. Falls back to character-based chunking
with overlap for sections that exceed CHUNK_SIZE, and for any page with no
detected headings at all.

Parameters (config.CHUNK_SIZE / config.CHUNK_OVERLAP) are deliberately
configurable rather than hard assumed-optimal values - see README for
tuning notes.
"""
import re
import config

# Matches lines like "1. Support terms" or "2. Cancellation terms" at line start.
SECTION_HEADING_RE = re.compile(r"(?m)^(\d{1,2})\.\s+(.+)$")


def split_into_sections(page_text: str):
    """Split page text into (heading, body) sections using numbered headings.
    If no headings are found, returns a single section with heading=None."""
    matches = list(SECTION_HEADING_RE.finditer(page_text))
    if not matches:
        return [(None, page_text)]

    sections = []
    # Preamble before the first heading (e.g. title/status lines)
    if matches[0].start() > 0:
        preamble = page_text[: matches[0].start()].strip()
        if preamble:
            sections.append(("Header", preamble))

    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(page_text)
        body = page_text[start:end].strip()
        sections.append((heading, body))
    return sections


def _char_chunk(text: str, chunk_size: int, overlap: int):
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def chunk_page(page_text: str, chunk_size: int = None, overlap: int = None):
    """Return list of dicts: {section, text} for a single page, using
    section-aware chunking with a character-based fallback for oversized
    sections."""
    chunk_size = chunk_size or config.CHUNK_SIZE
    overlap = overlap or config.CHUNK_OVERLAP

    chunks = []
    for heading, body in split_into_sections(page_text):
        for piece in _char_chunk(body, chunk_size, overlap):
            piece = piece.strip()
            if piece:
                chunks.append({"section": heading, "text": piece})
    return chunks

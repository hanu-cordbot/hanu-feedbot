"""Turns uploaded files into clean text chunks the question writer can cite from."""
import hashlib
import io
import re
from pathlib import PurePath

from . import config

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".csv", ".html", ".htm"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


class UnsupportedFile(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages)
    elif ext == ".docx":
        import docx

        document = docx.Document(io.BytesIO(data))
        text = "\n".join(p.text for p in document.paragraphs)
    elif ext in TEXT_EXTENSIONS:
        text = data.decode("utf-8", errors="replace")
        if ext in {".html", ".htm"}:
            text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
    else:
        raise UnsupportedFile(
            f"Can't read `{ext or filename}` files. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return normalize(text)


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\x00", "")
    # Re-join words hyphenated across PDF line breaks.
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = config.CHUNK_CHARS, overlap: int = config.CHUNK_OVERLAP) -> list[str]:
    """Splits on paragraph boundaries into ~size-char chunks with a little overlap,
    so a question's supporting passage is rarely cut in half."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > size:
            # One huge paragraph (common in PDFs): break it at a sentence end.
            cut = para.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            pieces = para[:cut].strip(), para[cut:].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(pieces[0])
            para = pieces[1]
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            tail = current[-overlap:]
            space = tail.find(" ")
            current = (tail[space + 1:] if space != -1 else tail) + "\n\n" + para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    # Fragments too small to write a question from are only noise.
    return [c for c in chunks if len(c) >= 200] or chunks


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

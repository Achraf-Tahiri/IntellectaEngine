"""Bounded, reportable PDF extraction and deterministic text chunking."""

from __future__ import annotations

import hashlib
import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from intellectaengine.config.settings import AppSettings, settings
from intellectaengine.core.contracts import ApplicationError, ErrorCode

logger = logging.getLogger(__name__)


def safe_display_name(value: object) -> str:
    """Return a display-only filename; it is never used to create a path."""
    name = os.path.basename(str(value or "document.pdf").replace("\\", "/")).replace("\x00", "")
    name = " ".join(name.split())
    return (name or "document.pdf")[:180]


@dataclass(frozen=True)
class FileIngestionOutcome:
    name: str
    status: str  # success | empty | unreadable | partial | limit_exceeded | duplicate
    pages: int = 0
    chunks: int = 0
    content_sha256: str | None = None


@dataclass
class ExtractionReport:
    outcomes: list[FileIngestionOutcome] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    files: int = 0
    pages: int = 0
    chunks: int = 0
    produced_chunks: int = 0  # Includes chunks discarded when a file exceeds a limit.

    @property
    def has_text(self) -> bool:
        return bool(self.documents)


class PDFConnector:
    """Extract PDFs without retaining uploads or leaking parser exceptions."""

    @classmethod
    def extract_and_split(
        cls,
        uploaded_files: list[Any],
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        config: AppSettings | None = None,
    ) -> ExtractionReport:
        config = config or settings
        size = config.rag_chunk_size if chunk_size is None else chunk_size
        overlap = config.rag_chunk_overlap if chunk_overlap is None else chunk_overlap
        cls._validate_splitter(size, overlap)
        report = ExtractionReport(files=len(uploaded_files))
        if len(uploaded_files) > config.rag_max_files:
            report.outcomes = [
                FileIngestionOutcome(
                    safe_display_name(getattr(item, "name", None)), "limit_exceeded"
                )
                for item in uploaded_files
            ]
            return report

        seen_content: set[str] = set()
        chunks_all: list[Document] = []
        outcomes: list[FileIngestionOutcome] = []
        for uploaded_file in uploaded_files:
            name = safe_display_name(getattr(uploaded_file, "name", uploaded_file))
            if (
                report.pages >= config.rag_max_pages
                or report.produced_chunks >= config.rag_max_chunks
            ):
                outcomes.append(FileIngestionOutcome(name, "limit_exceeded"))
                continue
            payload = cls._read_upload(uploaded_file, config.rag_max_upload_bytes)
            if payload is None:
                outcomes.append(FileIngestionOutcome(name, "unreadable"))
                continue
            if len(payload) > config.rag_max_upload_bytes:
                outcomes.append(FileIngestionOutcome(name, "limit_exceeded"))
                continue
            digest = hashlib.sha256(payload).hexdigest()
            if digest in seen_content:
                outcomes.append(FileIngestionOutcome(name, "duplicate", content_sha256=digest))
                continue
            seen_content.add(digest)
            chunks, status, page_count, produced = cls._extract_pages(
                payload,
                name,
                digest,
                size,
                overlap,
                config.rag_max_pages - report.pages,
                config.rag_max_chunks - report.produced_chunks,
            )
            report.pages += page_count
            report.produced_chunks += produced
            report.chunks += len(chunks)
            chunks_all.extend(chunks)
            outcomes.append(FileIngestionOutcome(name, status, page_count, len(chunks), digest))
        report.outcomes = outcomes
        report.documents = chunks_all
        return report

    @classmethod
    def load_and_split(
        cls, uploaded_files: list, chunk_size=None, chunk_overlap=None
    ) -> list[Document]:
        """Compatibility wrapper for callers that only need chunks."""
        return cls.extract_and_split(uploaded_files, chunk_size, chunk_overlap).documents

    @staticmethod
    def _validate_splitter(chunk_size: int, chunk_overlap: int) -> None:
        if not isinstance(chunk_size, int) or not isinstance(chunk_overlap, int):
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)
        if chunk_size < 100 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ApplicationError(ErrorCode.INVALID_CONFIGURATION)

    @staticmethod
    def _read_upload(uploaded_file: Any, max_bytes: int | None = None) -> bytes | None:
        """Read at most limit+1 bytes (one overflow sentinel), preserving seekable positions."""
        limit = settings.rag_max_upload_bytes if max_bytes is None else max_bytes
        try:
            position = None
            if hasattr(uploaded_file, "seek") and hasattr(uploaded_file, "tell"):
                position = uploaded_file.tell()
                uploaded_file.seek(0)
            try:
                parts = []
                remaining = limit + 1
                while remaining:
                    value = uploaded_file.read(remaining)
                    if not value:
                        break
                    parts.append(value[:remaining])
                    remaining -= len(parts[-1])
                return b"".join(parts)
            finally:
                if position is not None:
                    uploaded_file.seek(position)
        except Exception:
            return None

    @classmethod
    def _extract_pages(
        cls,
        payload: bytes,
        name: str,
        digest: str,
        size: int,
        overlap: int,
        page_budget: int,
        chunk_budget: int,
    ) -> tuple[list[Document], str, int, int]:
        attempted = 0
        chunks: list[Document] = []
        try:
            reader = PdfReader(io.BytesIO(payload))
            if reader.is_encrypted and reader.decrypt("") == 0:
                return [], "unreadable", 0, 0
            total = len(reader.pages)
            if total > page_budget:
                return [], "limit_exceeded", 0, 0
            failed = False
            for number in range(total):
                if len(chunks) >= chunk_budget:
                    return [], "limit_exceeded", attempted, len(chunks)
                attempted += 1
                try:
                    text = (reader.pages[number].extract_text() or "").strip()
                except Exception:
                    failed = True
                    continue
                if text:
                    page = Document(
                        page_content=text,
                        metadata={
                            "source": name,
                            "page": number,
                            "total_pages": total,
                            "content_sha256": digest,
                        },
                    )
                    produced, exceeded = cls._split_documents(
                        [page], size, overlap, chunk_budget - len(chunks)
                    )
                    chunks.extend(produced)
                    if exceeded:
                        return [], "limit_exceeded", attempted, len(chunks)
            if not chunks:
                return [], "unreadable" if failed else "empty", attempted, 0
            return chunks, "partial" if failed else "success", attempted, len(chunks)
        except (PdfReadError, ValueError, TypeError):
            return [], "unreadable", attempted, len(chunks)
        except Exception:
            logger.warning("PDF extraction failed for a user-selected file")
            return [], "unreadable", attempted, len(chunks)

    @staticmethod
    def _split_documents(
        documents: list[Document], chunk_size: int, chunk_overlap: int, max_chunks: int
    ) -> tuple[list[Document], bool]:
        """Split bounded windows; never materialize every chunk of a large page.

        Recursive splitting operates on at most four chunk sizes at a time.
        Adjacent windows overlap by the configured amount. This algorithm is
        versioned in the index format because window edges can change boundaries.
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
            length_function=len,
        )
        chunks: list[Document] = []
        for page in documents:
            text = page.page_content
            start = 0
            index = 0
            while start < len(text):
                if len(chunks) >= max_chunks:
                    return chunks, True
                end = min(len(text), start + 4 * chunk_size)
                for part in splitter.split_text(text[start:end]):
                    if len(chunks) >= max_chunks:
                        return chunks, True
                    metadata = dict(page.metadata)
                    identity = f"{metadata['content_sha256']}:{metadata['page']}:{index}:{part}"
                    metadata["chunk_id"] = hashlib.sha256(identity.encode()).hexdigest()
                    metadata["chunk_index"] = index
                    chunks.append(Document(page_content=part, metadata=metadata))
                    index += 1
                if end == len(text):
                    break
                start = end - chunk_overlap
        return chunks, False

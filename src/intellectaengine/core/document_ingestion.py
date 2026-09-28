"""Headless replace-on-success PDF knowledge-base lifecycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from intellectaengine.config.settings import AppSettings, settings
from intellectaengine.connectors.pdf_connector import ExtractionReport, FileIngestionOutcome
from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector
from intellectaengine.core.contracts import ApplicationError, ErrorCode
from intellectaengine.core.embedding_factory import EmbeddingFactory

_FORMAT = "intellectaengine-document-set-v2"


@dataclass(frozen=True)
class DocumentSet:
    collection_name: str
    session_id: str
    batch_identity: str
    config_identity: str
    embedding_provider: str
    embedding_model: str
    inventory: tuple[FileIngestionOutcome, ...]

    @property
    def names(self) -> list[str]:
        return [item.name for item in self.inventory if item.status in {"success", "partial"}]


@dataclass(frozen=True)
class IngestionResult:
    report: ExtractionReport
    document_set: DocumentSet | None
    vector_store: Any = None
    error: ErrorCode | None = None
    changed: bool = False
    cleanup_failed: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and self.document_set is not None


class DocumentIngestionService:
    """Build a new collection first, then let the caller swap its active handle."""

    @classmethod
    def upload_batch_identity(cls, uploaded_files: list[Any]) -> str | None:
        """Content-only identity used by the UI to mark an unsubmitted replacement."""
        from intellectaengine.connectors.pdf_connector import PDFConnector

        if len(uploaded_files) > settings.rag_max_files:
            return None
        digests = []
        for item in uploaded_files:
            payload = PDFConnector._read_upload(item)
            if payload is None or len(payload) > settings.rag_max_upload_bytes:
                return None
            digests.append(hashlib.sha256(payload).hexdigest())
        return cls._identity(sorted(set(digests)))

    @classmethod
    def replace(
        cls,
        uploaded_files: list[Any],
        session_id: str,
        embedding_provider: str,
        current: DocumentSet | None = None,
        embeddings: Any = None,
        embedding_model: str | None = None,
        config: AppSettings | None = None,
    ) -> IngestionResult:
        config = config or settings
        report = ExtractionReport()
        try:
            from intellectaengine.connectors.pdf_connector import PDFConnector

            report = PDFConnector.extract_and_split(uploaded_files, config=config)
            model = EmbeddingFactory.resolve_model(embedding_provider, embedding_model, config)
            config_identity = cls._configuration_identity(embedding_provider, model, config)
            successful = [
                outcome for outcome in report.outcomes if outcome.status in {"success", "partial"}
            ]
            batch_identity = cls._identity(
                sorted(item.content_sha256 for item in successful if item.content_sha256)
            )
            if not report.documents:
                return IngestionResult(report, current, error=ErrorCode.INGESTION_FAILURE)
            if (
                current
                and current.batch_identity == batch_identity
                and current.config_identity == config_identity
            ):
                store = cls.reopen(
                    current, session_id, embedding_provider, embeddings, model, config
                )
                if store is not None:
                    return IngestionResult(report, current, store, changed=False)
            embeddings = embeddings or EmbeddingFactory.create(embedding_provider, model, config)
            collection_name = VectorStoreConnector.build_collection_name(
                session_id, cls._identity({"batch": batch_identity, "config": config_identity})
            )
            metadata = {
                "format": _FORMAT,
                "session_id": session_id,
                "batch_identity": batch_identity,
                "config_identity": config_identity,
                "embedding_provider": embedding_provider.lower(),
                "embedding_model": model,
                "chunk_size": config.rag_chunk_size,
                "chunk_overlap": config.rag_chunk_overlap,
            }
            # Content/config identity makes repeat calls use the no-reembed reopen branch above.
            store = VectorStoreConnector.create(
                report.documents, embeddings, collection_name, metadata, config
            )
            document_set = DocumentSet(
                collection_name,
                session_id,
                batch_identity,
                config_identity,
                embedding_provider.lower(),
                model,
                tuple(successful),
            )
            cleanup_failed = bool(
                current
                and current.collection_name != collection_name
                and not cls.clear(current, config)
            )
            return IngestionResult(
                report, document_set, store, changed=True, cleanup_failed=cleanup_failed
            )
        except ApplicationError as exc:
            return IngestionResult(report, current, error=exc.code)
        except Exception:
            return IngestionResult(report, current, error=ErrorCode.INDEX_FAILURE)

    @classmethod
    def reopen(
        cls,
        document_set: DocumentSet,
        session_id: str,
        embedding_provider: str,
        embeddings: Any = None,
        embedding_model: str | None = None,
        config: AppSettings | None = None,
    ) -> Any | None:
        config = config or settings
        if document_set.session_id != session_id:
            return None
        model = EmbeddingFactory.resolve_model(embedding_provider, embedding_model, config)
        if (
            document_set.embedding_provider != embedding_provider.lower()
            or document_set.embedding_model != model
            or document_set.config_identity
            != cls._configuration_identity(embedding_provider, model, config)
        ):
            return None
        expected = {
            "format": _FORMAT,
            "session_id": session_id,
            "batch_identity": document_set.batch_identity,
            "config_identity": document_set.config_identity,
            "embedding_provider": document_set.embedding_provider,
            "embedding_model": document_set.embedding_model,
            "expected_chunks": sum(item.chunks for item in document_set.inventory),
        }
        try:
            return VectorStoreConnector.load(
                embeddings or EmbeddingFactory.create(embedding_provider, model, config),
                document_set.collection_name,
                expected,
                config,
            )
        except ApplicationError:
            return None

    @staticmethod
    def clear(document_set: DocumentSet | None, config: AppSettings | None = None) -> bool:
        return document_set is None or VectorStoreConnector.delete_collection(
            document_set.collection_name, config
        )

    @staticmethod
    def _identity(value: object) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:24]

    @classmethod
    def _configuration_identity(cls, provider: str, model: str, config: AppSettings) -> str:
        return cls._identity(
            {
                "provider": provider.lower(),
                "model": model,
                "chunk_size": config.rag_chunk_size,
                "chunk_overlap": config.rag_chunk_overlap,
                "format": _FORMAT,
            }
        )

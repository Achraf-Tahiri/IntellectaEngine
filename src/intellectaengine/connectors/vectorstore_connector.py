"""Supported embedded-Chroma collection lifecycle with confined storage."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from intellectaengine.config.settings import AppSettings, settings
from intellectaengine.core.contracts import ApplicationError, ErrorCode

logger = logging.getLogger(__name__)
_SAFE_COLLECTION = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")


class VectorStoreConnector:
    """Use Chroma's collection APIs; a collection is not a filesystem directory."""

    @classmethod
    def create(
        cls,
        documents: list[Document],
        embeddings: Embeddings,
        collection_name: str,
        metadata: dict[str, Any],
        config: AppSettings | None = None,
    ) -> Chroma:
        if not documents:
            raise ValueError("A collection requires at least one document.")
        cls._validate_name(collection_name)
        ids = [str(document.metadata["chunk_id"]) for document in documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Chunk identifiers must be unique.")
        owned = None
        try:
            client = cls._client(config)
            manifest = {
                **metadata,
                "lifecycle": "building",
                "expected_chunks": len(ids),
                "chunk_ids_sha256": cls._ids_digest(ids),
            }
            # Exclusive API: never get-or-create. A collision confers no ownership,
            # regardless of whether the existing collection is complete or abandoned.
            owned = client.create_collection(
                collection_name, metadata=manifest, embedding_function=None
            )
            store = Chroma(
                collection_name=collection_name,
                client=client,
                embedding_function=embeddings,
                create_collection_if_not_exists=False,
            )
            store.add_documents(documents, ids=ids)
            if not cls._matches_manifest(owned, manifest):
                raise ApplicationError(ErrorCode.INDEX_FAILURE)
            owned.modify(metadata={**manifest, "lifecycle": "ready"})
            return store
        except Exception:
            if owned is not None:
                # Do not remove a different collection recreated under the same name.
                try:
                    current = client.get_collection(collection_name)
                    if current.id == owned.id:
                        client.delete_collection(collection_name)
                        try:
                            client.get_collection(collection_name)
                        except NotFoundError:
                            pass
                        else:
                            logger.warning("Incomplete index cleanup could not be verified")
                except NotFoundError:
                    pass
                except Exception:
                    logger.warning("Incomplete index cleanup failed")
            raise ApplicationError(ErrorCode.INDEX_FAILURE) from None

    @classmethod
    def load(
        cls,
        embeddings: Embeddings,
        collection_name: str,
        expected_metadata: dict[str, Any] | None = None,
        config: AppSettings | None = None,
    ) -> Chroma | None:
        cls._validate_name(collection_name)
        try:
            client = cls._client(config)
            collection = client.get_collection(collection_name)
            metadata = collection.metadata or {}
            if metadata.get("lifecycle") != "ready" or not cls._matches_manifest(
                collection, metadata
            ):
                return None
            if expected_metadata and any(
                metadata.get(key) != value for key, value in expected_metadata.items()
            ):
                return None
            return Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                client=client,
                create_collection_if_not_exists=False,
            )
        except Exception:
            return None

    @classmethod
    def delete_collection(cls, collection_name: str, config: AppSettings | None = None) -> bool:
        """Delete only a validated named collection and verify it is gone."""
        try:
            cls._validate_name(collection_name)
            client = cls._client(config)
            try:
                client.get_collection(collection_name)
            except NotFoundError:
                return True
            client.delete_collection(collection_name)
            try:
                client.get_collection(collection_name)
            except NotFoundError:
                return True
        except Exception:
            logger.warning("Chroma collection deletion failed")
        return False

    @classmethod
    def collection_exists(cls, collection_name: str, config: AppSettings | None = None) -> bool:
        cls._validate_name(collection_name)
        try:
            cls._client(config).get_collection(collection_name)
            return True
        except NotFoundError:
            return False
        except Exception:
            raise ApplicationError(ErrorCode.INDEX_FAILURE) from None

    @classmethod
    def collection_metadata(
        cls, collection_name: str, config: AppSettings | None = None
    ) -> dict[str, Any] | None:
        cls._validate_name(collection_name)
        try:
            return dict(cls._client(config).get_collection(collection_name).metadata or {})
        except NotFoundError:
            return None
        except Exception:
            raise ApplicationError(ErrorCode.INDEX_FAILURE) from None

    @staticmethod
    def _ids_digest(ids: list[str]) -> str:
        return hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def _matches_manifest(cls, collection, metadata: dict[str, Any]) -> bool:
        expected = metadata.get("expected_chunks")
        if type(expected) is not int or expected <= 0 or collection.count() != expected:
            return False
        # No document text or vectors need to be loaded for this completeness check.
        ids = collection.get(include=[])["ids"]
        return len(ids) == expected and cls._ids_digest(ids) == metadata.get("chunk_ids_sha256")

    @staticmethod
    def build_collection_name(session_id: str, identity: str) -> str:
        session = "".join(char for char in session_id.lower() if char.isalnum())[:24]
        suffix = "".join(char for char in identity.lower() if char.isalnum())[:24]
        name = f"ie-{session}-{suffix}"
        if not _SAFE_COLLECTION.fullmatch(name):
            raise ValueError("Invalid collection identity.")
        return name

    @classmethod
    def get_or_create(
        cls, documents: list[Document], embeddings: Embeddings, collection_name: str
    ) -> VectorStore:
        """Legacy helper: load only; it never silently appends documents."""
        existing = cls.load(embeddings, collection_name)
        return (
            existing
            if existing is not None
            else cls.create(documents, embeddings, collection_name, {})
        )

    @classmethod
    def _client(cls, config: AppSettings | None) -> chromadb.PersistentClient:
        root = cls._storage_root(config)
        return chromadb.PersistentClient(
            path=str(root),
            settings=Settings(anonymized_telemetry=False),
        )

    @staticmethod
    def _storage_root(config: AppSettings | None) -> Path:
        configured = Path((config or settings).chroma_persist_base_dir).expanduser()
        root = configured.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _validate_name(collection_name: str) -> None:
        if not isinstance(collection_name, str) or not _SAFE_COLLECTION.fullmatch(collection_name):
            raise ValueError("Invalid collection name.")

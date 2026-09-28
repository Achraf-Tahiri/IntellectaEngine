"""Curated source facts survive real ingestion; SQL references use the native policy."""

from io import BytesIO
import json


def test_curated_pdf_ingests_original_text_and_page_metadata(project_root, tmp_path):
    from langchain_core.embeddings import DeterministicFakeEmbedding

    from intellectaengine.config.settings import AppSettings
    from intellectaengine.core.document_ingestion import DocumentIngestionService

    config = AppSettings(_env_file=None, chroma_persist_base_dir=str(tmp_path / "chroma"))
    upload = BytesIO((project_root / "examples/field-notes.pdf").read_bytes())
    upload.name = "field-notes.pdf"
    result = DocumentIngestionService.replace(
        [upload],
        "example-verification",
        "huggingface",
        embeddings=DeterministicFakeEmbedding(size=8),
        config=config,
    )
    try:
        assert result.ok
        assert result.report.pages == 2
        assert [item.status for item in result.report.outcomes] == ["success"]
        indexed = result.vector_store.get()
        pages = {}
        for text, metadata in zip(indexed["documents"], indexed["metadatas"], strict=True):
            assert metadata["source"] == "field-notes.pdf"
            pages.setdefault(metadata["page"], []).append(text)
        # Match every source paragraph to its original page, ignoring layout whitespace.
        original = (project_root / "examples/field-notes.txt").read_text().strip()
        for page, source in enumerate(original.split("\n---\n")):
            extracted = " ".join(" ".join(pages[page]).split())
            for line in source.strip().splitlines():
                if line.strip():
                    assert " ".join(line.split()) in extracted
        assert "24 kits" in " ".join(pages[0])
        assert "36 completed loans" in " ".join(pages[1])
        assert "does not set a budget" in " ".join(pages[1])
    finally:
        assert DocumentIngestionService.clear(result.document_set, config)


def test_curated_chinook_reference_queries_through_read_only_policy(project_root):
    from intellectaengine.core.sql_policy import SAMPLE_DB, SQLitePolicy

    queries = json.loads((project_root / "examples/chinook-queries.json").read_text())
    policy = SQLitePolicy()
    for example in queries:
        assert policy.query(SAMPLE_DB, example["sql"]).strip() == example["expected"]

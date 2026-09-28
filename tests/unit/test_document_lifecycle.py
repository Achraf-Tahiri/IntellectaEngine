"""Offline regression coverage for the Phase 4 PDF lifecycle boundary."""

from io import BytesIO
from types import SimpleNamespace

import pytest

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def pdf_bytes(text: str | None) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(200, 200)
    if text is not None:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        reference = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): reference})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class Upload(BytesIO):
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


class CountingEmbeddings:
    def __init__(self):
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        return [[float(len(text) % 13), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text) % 13), 1.0]


def local_config(tmp_path, **overrides):
    from intellectaengine.config.settings import AppSettings

    values = {
        "_env_file": None,
        "chroma_persist_base_dir": str(tmp_path / "chroma"),
        "rag_chunk_size": 100,
        "rag_chunk_overlap": 0,
    }
    values.update(overrides)
    return AppSettings(**values)


def test_report_handles_text_empty_corrupt_duplicate_and_zero_overlap(tmp_path):
    from intellectaengine.connectors.pdf_connector import PDFConnector

    config = local_config(tmp_path)
    valid = pdf_bytes("evidence " * 30)
    report = PDFConnector.extract_and_split(
        [
            Upload(valid, "../report.pdf"),
            Upload(pdf_bytes(None), "scan.pdf"),
            Upload(b"not a PDF", "bad.pdf"),
            Upload(valid, "renamed.pdf"),
        ],
        chunk_size=100,
        chunk_overlap=0,
        config=config,
    )
    assert [item.status for item in report.outcomes] == [
        "success",
        "empty",
        "unreadable",
        "duplicate",
    ]
    assert report.documents and report.documents[0].metadata["source"] == "report.pdf"
    assert all("chunk_id" in document.metadata for document in report.documents)


def test_limits_and_invalid_splitter_are_reported_or_rejected(tmp_path):
    import pytest

    from intellectaengine.connectors.pdf_connector import PDFConnector
    from intellectaengine.core.contracts import ApplicationError

    config = local_config(tmp_path, rag_max_files=1)
    report = PDFConnector.extract_and_split(
        [Upload(pdf_bytes("a"), "a.pdf"), Upload(pdf_bytes("b"), "b.pdf")], config=config
    )
    assert {item.status for item in report.outcomes} == {"limit_exceeded"}
    with pytest.raises(ApplicationError):
        PDFConnector.extract_and_split(
            [Upload(pdf_bytes("a"), "a.pdf")], chunk_size=100, chunk_overlap=100, config=config
        )


def test_replacement_reopen_and_clear_use_real_chroma_without_reembedding(tmp_path):
    from intellectaengine.core.document_ingestion import DocumentIngestionService

    config = local_config(tmp_path)
    embeddings = CountingEmbeddings()
    first = DocumentIngestionService.replace(
        [Upload(pdf_bytes("first facts"), "a.pdf")],
        "session-a",
        "huggingface",
        embeddings=embeddings,
        config=config,
    )
    assert first.ok and first.changed and embeddings.calls == 1
    again = DocumentIngestionService.replace(
        [Upload(pdf_bytes("first facts"), "renamed.pdf")],
        "session-a",
        "huggingface",
        current=first.document_set,
        embeddings=embeddings,
        config=config,
    )
    assert again.ok and not again.changed and embeddings.calls == 1
    assert again.document_set.names == ["a.pdf"]
    assert (
        DocumentIngestionService.reopen(
            first.document_set, "other-session", "huggingface", embeddings, config=config
        )
        is None
    )
    assert DocumentIngestionService.clear(first.document_set, config)
    assert (
        DocumentIngestionService.reopen(
            first.document_set, "session-a", "huggingface", embeddings, config=config
        )
        is None
    )


def test_failed_replacement_preserves_caller_owned_active_set(tmp_path):
    from intellectaengine.core.document_ingestion import DocumentIngestionService
    from intellectaengine.core.contracts import ErrorCode

    config = local_config(tmp_path)
    embeddings = CountingEmbeddings()
    active = DocumentIngestionService.replace(
        [Upload(pdf_bytes("facts"), "a.pdf")],
        "session-a",
        "huggingface",
        embeddings=embeddings,
        config=config,
    )
    failed = DocumentIngestionService.replace(
        [Upload(b"bad", "bad.pdf")],
        "session-a",
        "huggingface",
        current=active.document_set,
        embeddings=embeddings,
        config=config,
    )
    assert (
        failed.error == ErrorCode.INGESTION_FAILURE and failed.document_set == active.document_set
    )
    assert active.vector_store.similarity_search("facts", k=1)


def test_replacement_removes_old_collection_and_rejects_incompatible_reopen(tmp_path):
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector
    from intellectaengine.core.document_ingestion import DocumentIngestionService

    config = local_config(tmp_path)
    embeddings = CountingEmbeddings()
    first = DocumentIngestionService.replace(
        [Upload(pdf_bytes("old facts"), "old.pdf")],
        "session-a",
        "huggingface",
        embeddings=embeddings,
        config=config,
    )
    second = DocumentIngestionService.replace(
        [Upload(pdf_bytes("new facts"), "new.pdf")],
        "session-a",
        "huggingface",
        current=first.document_set,
        embeddings=embeddings,
        config=config,
    )
    assert second.ok and second.document_set.names == ["new.pdf"]
    assert not VectorStoreConnector.collection_exists(first.document_set.collection_name, config)
    assert (
        DocumentIngestionService.reopen(
            second.document_set, "session-a", "fastembed", embeddings, config=config
        )
        is None
    )
    changed_splitter = local_config(tmp_path, rag_chunk_size=101)
    assert (
        DocumentIngestionService.reopen(
            second.document_set, "session-a", "huggingface", embeddings, config=changed_splitter
        )
        is None
    )


def test_rag_context_is_bounded_and_references_are_one_based(monkeypatch):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.documents import Document
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.tools.rag_tool import RAGTool
    from intellectaengine.config.settings import settings

    prompts = []

    class Recorder(BaseCallbackHandler):
        def on_llm_start(self, serialized, incoming, **kwargs):
            prompts.extend(incoming)

    class Retriever:
        def invoke(self, query):
            return [
                Document(page_content="x" * 20_000, metadata={"source": "../paper.pdf", "page": 0})
            ]

    class Store:
        def as_retriever(self, **kwargs):
            return Retriever()

    result = RAGTool.run(
        "question",
        Store(),
        FakeListLLM(responses=["answer"], callbacks=[Recorder()]),
        return_result=True,
    )
    context = (
        prompts[0]
        .split("Retrieved context begins:\n", 1)[1]
        .split("\nRetrieved context ends.", 1)[0]
    )
    assert len(context) <= settings.rag_context_char_limit
    assert "[Retrieved source: paper.pdf; page: 1]" in context
    assert result.sources[0].source == "paper.pdf" and result.sources[0].page == 1
    assert "p. 1" in result.answer
    monkeypatch.setattr(RAGTool, "_retrieve_bounded", lambda *args: [])
    empty = RAGTool.run(
        "question", Store(), FakeListLLM(responses=["unsupported"]), return_result=True
    )
    assert not empty.sources and "could not find" in empty.answer.lower()


def test_automatic_router_preserves_rag_evidence_separately_from_model_output():
    from langchain_core.documents import Document
    from langchain_core.language_models.fake import FakeListLLM

    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext

    class Retriever:
        def invoke(self, query):
            return [Document(page_content="fact", metadata={"source": "evidence.pdf", "page": 2})]

    class Store:
        def as_retriever(self, **kwargs):
            return Retriever()

    model = FakeListLLM(
        responses=[
            "Action: rag_document_search\nAction Input: question",
            "tool answer",
            "Final Answer: concise answer without citations",
        ]
    )
    result = ApplicationService.run(
        "question",
        "ollama",
        context=AgentContext(vector_store=Store()),
        llm_factory=lambda **_: model,
    )
    assert result.ok and result.answer == "concise answer without citations"
    assert [(source.source, source.page) for source in result.sources] == [("evidence.pdf", 3)]


def test_failed_embedding_cleanup_allows_retry_and_preserves_report(tmp_path, caplog):
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V
    from intellectaengine.core.document_ingestion import DocumentIngestionService as S

    config = local_config(tmp_path)
    embeddings = CountingEmbeddings()
    active = S.replace(
        [Upload(pdf_bytes("old"), "old.pdf")],
        "session",
        "huggingface",
        embeddings=embeddings,
        config=config,
    )

    class Broken(CountingEmbeddings):
        def embed_documents(self, texts):
            raise RuntimeError("SYNTHETIC-SECRET /private/path document contents")

    batch = [Upload(pdf_bytes("new"), "new.pdf")]
    failed = S.replace(
        batch,
        "session",
        "huggingface",
        current=active.document_set,
        embeddings=Broken(),
        config=config,
    )
    assert active.vector_store.similarity_search("old", k=1)[0].page_content == "old"
    assert active.document_set.names == ["old.pdf"]
    client = V._client(config)
    assert len(client.list_collections()) == 1  # Only the prior usable index remains.
    retry = S.replace(
        batch,
        "session",
        "huggingface",
        current=active.document_set,
        embeddings=embeddings,
        config=config,
    )
    assert retry.ok
    assert failed.document_set == active.document_set and not failed.ok
    assert failed.report.chunks == 1 and failed.report.outcomes[0].name == "new.pdf"
    assert "SYNTHETIC-SECRET" not in caplog.text + str(failed.error)
    assert V.collection_exists(retry.document_set.collection_name, config)


@pytest.mark.parametrize("state", ["building", "ready"])
def test_collisions_are_neither_adopted_nor_deleted(tmp_path, monkeypatch, state):
    from intellectaengine.connectors.pdf_connector import PDFConnector
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V
    from intellectaengine.core.document_ingestion import DocumentIngestionService as S

    config = local_config(tmp_path)
    embeddings = CountingEmbeddings()
    active = S.replace(
        [Upload(pdf_bytes("old"), "old.pdf")],
        "session",
        "huggingface",
        embeddings=embeddings,
        config=config,
    )
    client = V._client(config)
    if state == "building":
        client.create_collection(
            "collision-index", metadata={"lifecycle": state}, embedding_function=None
        )
    else:
        docs = PDFConnector.extract_and_split(
            [Upload(pdf_bytes("unrelated"), "other.pdf")], config=config
        ).documents
        V.create(docs, embeddings, "collision-index", {"owner": "unrelated"}, config)
    collision = client.get_collection("collision-index")
    before = collision.get(include=["documents", "metadatas"])
    monkeypatch.setattr(V, "build_collection_name", lambda *args: "collision-index")
    result = S.replace(
        [Upload(pdf_bytes("new"), "new.pdf")],
        "session",
        "huggingface",
        current=active.document_set,
        embeddings=embeddings,
        config=config,
    )
    assert not result.ok and result.document_set == active.document_set
    after = client.get_collection("collision-index")
    assert after.id == collision.id and after.metadata == collision.metadata
    assert after.get(include=["documents", "metadatas"]) == before
    assert active.vector_store.similarity_search("old", k=1)[0].page_content == "old"
    if state == "building":
        assert V.load(embeddings, "collision-index", config=config) is None


@pytest.mark.parametrize("damage", ["building", "missing_chunk", "wrong_id", "missing_manifest"])
def test_reopen_requires_complete_manifest(tmp_path, damage):
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V
    from intellectaengine.core.document_ingestion import DocumentIngestionService as S

    config = local_config(tmp_path)
    embeddings = CountingEmbeddings()
    active = S.replace(
        [Upload(pdf_bytes("fact"), "a.pdf")],
        "session",
        "huggingface",
        embeddings=embeddings,
        config=config,
    )
    collection = V._client(config).get_collection(active.document_set.collection_name)
    if damage == "building":
        collection.modify(metadata={**collection.metadata, "lifecycle": "building"})
    elif damage == "missing_manifest":
        collection.modify(metadata={"format": "legacy"})
    else:
        collection.delete(ids=collection.get(include=[])["ids"])
        if damage == "wrong_id":
            collection.add(ids=["wrong"], documents=["fact"], embeddings=[[1.0, 1.0]])
    assert (
        S.reopen(active.document_set, "session", "huggingface", embeddings, config=config) is None
    )


def test_actual_chroma_not_found_is_idempotent_deletion(tmp_path):
    from chromadb.errors import NotFoundError
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V

    config = local_config(tmp_path)
    client = V._client(config)
    with pytest.raises(NotFoundError):
        client.get_collection("absent-index")
    assert V.delete_collection("absent-index", config)
    client.create_collection("test-index", embedding_function=None)
    assert V.delete_collection("test-index", config)
    with pytest.raises(NotFoundError):
        client.get_collection("test-index")
    assert V.delete_collection("test-index", config)


def test_cleanup_failure_leaves_unadoptable_collection_and_safe_diagnostics(
    tmp_path, monkeypatch, caplog
):
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V
    from intellectaengine.core.document_ingestion import DocumentIngestionService as S

    config = local_config(tmp_path)
    client = V._client(config)

    class Broken(CountingEmbeddings):
        def embed_documents(self, texts):
            raise RuntimeError("SYNTHETIC-SECRET embed")

    def fail_delete(name):
        raise RuntimeError("SYNTHETIC-SECRET delete")

    monkeypatch.setattr(V, "_client", lambda config: client)
    monkeypatch.setattr(client, "delete_collection", fail_delete)
    result = S.replace(
        [Upload(pdf_bytes("fact"), "a.pdf")],
        "session",
        "huggingface",
        embeddings=Broken(),
        config=config,
    )
    assert not result.ok and result.report.chunks == 1
    collection = client.list_collections()[0]
    assert collection.metadata["lifecycle"] == "building"
    assert V.load(CountingEmbeddings(), collection.name, config=config) is None
    assert "cleanup failed" in caplog.text and "SYNTHETIC-SECRET" not in caplog.text


@pytest.mark.parametrize("stage", ["client", "lookup", "delete", "verification"])
def test_deletion_errors_never_establish_absence(monkeypatch, stage, caplog):
    from intellectaengine.connectors.vectorstore_connector import VectorStoreConnector as V

    calls = []

    def fail():
        raise RuntimeError("SYNTHETIC-SECRET storage outage")

    def lookup(name):
        calls.append(name)
        if stage == "lookup" or (stage == "verification" and len(calls) == 2):
            fail()
        return object()

    def delete(name):
        if stage == "delete":
            fail()

    def client(config):
        if stage == "client":
            fail()
        return SimpleNamespace(get_collection=lookup, delete_collection=delete)

    monkeypatch.setattr(V, "_client", client)
    assert V.delete_collection("test-index") is False
    assert "SYNTHETIC-SECRET" not in caplog.text


def test_reused_context_has_no_transient_evidence():
    from langchain_core.documents import Document
    from langchain_core.language_models.fake import FakeListLLM
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext

    store = SimpleNamespace(
        as_retriever=lambda **_: SimpleNamespace(
            invoke=lambda q: [
                Document(page_content="fact", metadata={"source": "first.pdf", "page": 0})
            ]
        )
    )
    context = AgentContext(vector_store=store, extra={"caller": "retained"})
    model = FakeListLLM(
        responses=[
            "Action: rag_document_search\nAction Input: q",
            "fact",
            "Final Answer: first",
            "Final Answer: second",
        ]
    )
    first = ApplicationService.run("q", "ollama", context=context, llm_factory=lambda **_: model)
    second = ApplicationService.run("q", "ollama", context=context, llm_factory=lambda **_: model)
    assert first.sources
    assert second.sources == ()
    assert context.extra == {"caller": "retained"}


def test_page_limit_precedes_extraction(monkeypatch, tmp_path):
    import intellectaengine.connectors.pdf_connector as pdf

    calls = []
    pages = [SimpleNamespace(extract_text=lambda: calls.append(1) or "text") for _ in range(3)]
    monkeypatch.setattr(
        pdf, "PdfReader", lambda _: SimpleNamespace(is_encrypted=False, pages=pages)
    )
    report = pdf.PDFConnector.extract_and_split(
        [Upload(b"synthetic", "large.pdf")], config=local_config(tmp_path, rag_max_pages=1)
    )
    assert calls == []
    assert report.outcomes[0].status == "limit_exceeded"


def test_upload_read_is_bounded(tmp_path):
    from intellectaengine.connectors.pdf_connector import PDFConnector

    requests = []

    class Stream:
        name = "large.pdf"

        def read(self, size=-1):
            requests.append(size)
            return b"x" * (size if size >= 0 else 1000)

    report = PDFConnector.extract_and_split(
        [Stream()], config=local_config(tmp_path, rag_max_upload_bytes=10)
    )
    assert requests == [11]
    assert report.outcomes[0].status == "limit_exceeded"


def test_chunk_budget_bounds_splitter_work_and_later_extraction(monkeypatch, tmp_path):
    import intellectaengine.connectors.pdf_connector as pdf

    calls = []
    split_lengths = []

    def extract():
        calls.append(1)
        return "word " * 100_000

    monkeypatch.setattr(
        pdf,
        "PdfReader",
        lambda _: SimpleNamespace(
            is_encrypted=False,
            pages=[SimpleNamespace(extract_text=extract), SimpleNamespace(extract_text=extract)],
        ),
    )
    original = pdf.RecursiveCharacterTextSplitter.split_text

    def split(self, text):
        split_lengths.append(len(text))
        return original(self, text)

    monkeypatch.setattr(pdf.RecursiveCharacterTextSplitter, "split_text", split)
    report = pdf.PDFConnector.extract_and_split(
        [Upload(b"pdf", "huge.pdf")], config=local_config(tmp_path, rag_max_chunks=1)
    )
    assert calls == [1]
    assert max(split_lengths) <= 400
    assert not report.documents and report.outcomes[0].status == "limit_exceeded"


def test_partial_and_empty_pages_consume_aggregate_page_budget(monkeypatch, tmp_path, caplog):
    import intellectaengine.connectors.pdf_connector as pdf

    calls = []

    def bad():
        calls.append("bad")
        raise RuntimeError("SYNTHETIC-SECRET page text")

    def good():
        calls.append("good")
        return "evidence"

    readers = iter(
        [
            SimpleNamespace(is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda: "")]),
            SimpleNamespace(
                is_encrypted=False,
                pages=[SimpleNamespace(extract_text=bad), SimpleNamespace(extract_text=good)],
            ),
        ]
    )
    monkeypatch.setattr(pdf, "PdfReader", lambda _: next(readers))
    report = pdf.PDFConnector.extract_and_split(
        [
            Upload(b"empty", "empty.pdf"),
            Upload(b"partial", "partial.pdf"),
            Upload(b"skip", "skip.pdf"),
        ],
        config=local_config(tmp_path, rag_max_pages=3),
    )
    assert calls == ["bad", "good"]
    assert [o.status for o in report.outcomes] == ["empty", "partial", "limit_exceeded"]
    assert report.pages == sum(o.pages for o in report.outcomes) == 3
    assert report.chunks == report.produced_chunks == 1
    assert report.documents[0].metadata["page"] == 1
    assert "SYNTHETIC-SECRET" not in caplog.text


def test_chunk_work_is_not_refunded_when_a_file_is_discarded(monkeypatch, tmp_path):
    import intellectaengine.connectors.pdf_connector as pdf

    readers = []

    def reader(_):
        readers.append(1)
        text = "small" if len(readers) == 1 else "x" * 1000
        return SimpleNamespace(
            is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda: text)]
        )

    monkeypatch.setattr(pdf, "PdfReader", reader)
    report = pdf.PDFConnector.extract_and_split(
        [Upload(b"one", "one.pdf"), Upload(b"two", "two.pdf"), Upload(b"three", "three.pdf")],
        config=local_config(tmp_path, rag_max_chunks=2),
    )
    assert [o.status for o in report.outcomes] == ["success", "limit_exceeded", "limit_exceeded"]
    assert len(readers) == 2
    assert report.produced_chunks == 2 and report.chunks == 1
    assert report.pages == sum(o.pages for o in report.outcomes) == 2
    assert [doc.metadata["source"] for doc in report.documents] == ["one.pdf"]


def test_encrypted_pdf_is_reported_without_extracting(tmp_path):
    from pypdf import PdfReader
    from intellectaengine.connectors.pdf_connector import PDFConnector

    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(pdf_bytes("protected"))))
    writer.encrypt("synthetic-password")
    encrypted = BytesIO()
    writer.write(encrypted)
    report = PDFConnector.extract_and_split(
        [Upload(encrypted.getvalue(), "locked.pdf")], config=local_config(tmp_path)
    )
    assert report.outcomes[0].status == "unreadable"
    assert report.pages == report.chunks == 0 and not report.documents


def test_zero_overlap_and_stable_chunk_ids_across_bounded_windows(tmp_path):
    from intellectaengine.connectors.pdf_connector import PDFConnector

    text = "abcdefghij" * 110
    upload = Upload(pdf_bytes(text), "long.pdf")
    config = local_config(tmp_path)
    first = PDFConnector.extract_and_split([upload], config=config, chunk_overlap=0)
    second = PDFConnector.extract_and_split([upload], config=config, chunk_overlap=0)
    assert "".join(d.page_content for d in first.documents) == text
    assert len(first.documents) == 11
    assert [d.metadata["chunk_id"] for d in first.documents] == [
        d.metadata["chunk_id"] for d in second.documents
    ]


def test_bounded_reads_handle_short_reads_and_restore_position(tmp_path):
    from intellectaengine.connectors.pdf_connector import PDFConnector

    requests = []

    class ShortStream(Upload):
        def read(self, size=-1):
            assert size > 0
            requests.append(size)
            return super().read(min(3, size))

        def getvalue(self):
            pytest.fail("Unbounded getvalue must not be called")

    stream = ShortStream(b"x" * 30, "big.pdf")
    stream.seek(2)
    report = PDFConnector.extract_and_split(
        [stream], config=local_config(tmp_path, rag_max_upload_bytes=10)
    )
    assert requests == [11, 8, 5, 2] and stream.tell() == 2
    assert report.outcomes[0].status == "limit_exceeded"


@pytest.mark.parametrize("failure", [False, True])
def test_multiple_rag_calls_deduplicate_and_never_leak_after_failure_or_retry(failure):
    from langchain_core.documents import Document
    from langchain_core.language_models.fake import FakeListLLM
    from intellectaengine.core.application import ApplicationService
    from intellectaengine.core.contracts import AgentContext

    def retrieve(query):
        if query == "broken":
            raise RuntimeError("SYNTHETIC-SECRET retrieval")
        return [
            Document(page_content="fact", metadata={"source": name, "page": 0})
            for name in (["first.pdf"] if query == "first" else ["first.pdf", "second.pdf"])
        ]

    store = SimpleNamespace(as_retriever=lambda **_: SimpleNamespace(invoke=retrieve))
    ctx = AgentContext(vector_store=store, extra={"caller": ["data"]})
    responses = [
        "Action: rag_document_search\nAction Input: first",
        "answer one",
        f"Action: rag_document_search\nAction Input: {'broken' if failure else 'second'}",
    ]
    if not failure:
        responses += ["answer two", "Final Answer: combined"]
    result = ApplicationService.run(
        "q", "ollama", context=ctx, llm_factory=lambda **_: FakeListLLM(responses=responses)
    )
    if failure:
        assert not result.ok and result.sources == ()
    else:
        assert result.ok
        assert [r.source for r in result.sources] == ["first.pdf", "second.pdf"]
    direct = ApplicationService.run(
        "q",
        "ollama",
        context=ctx,
        llm_factory=lambda **_: FakeListLLM(responses=["Final Answer: direct"]),
    )
    assert direct.ok and direct.sources == ()
    forced = ApplicationService.run(
        "first",
        "ollama",
        context=ctx,
        mode="rag",
        llm_factory=lambda **_: FakeListLLM(responses=["forced answer"]),
    )
    assert forced.ok and [r.source for r in forced.sources] == ["first.pdf"]
    assert ctx.extra == {"caller": ["data"]} and ctx.memory.get_history() == []


def test_context_budget_includes_separators_missing_metadata_and_only_used_sources(monkeypatch):
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.documents import Document
    from langchain_core.language_models.fake import FakeListLLM
    from intellectaengine.config.settings import settings
    from intellectaengine.tools.rag_tool import RAGTool

    monkeypatch.setattr(settings, "rag_context_char_limit", 150)
    prompts = []

    class Recorder(BaseCallbackHandler):
        def on_llm_start(self, serialized, incoming, **kwargs):
            prompts.extend(incoming)

    docs = [
        Document(page_content="empty metadata"),
        Document(page_content="evidence " * 100, metadata={"source": "used.pdf"}),
        Document(page_content="excluded", metadata={"source": "excluded.pdf", "page": 8}),
    ]
    store = SimpleNamespace(as_retriever=lambda **_: SimpleNamespace(invoke=lambda q: docs))
    result = RAGTool.run(
        "q",
        store,
        FakeListLLM(responses=["answer"], callbacks=[Recorder()]),
        pdf_names=["fabricated.pdf"],
        return_result=True,
    )
    context = (
        prompts[0]
        .split("Retrieved context begins:\n", 1)[1]
        .split("\nRetrieved context ends.", 1)[0]
    )
    assert len(context) == 150 and "\n\n" in context
    assert "source: unavailable; page: unavailable" in context
    assert "excluded" not in context and "fabricated" not in result.answer + context
    assert [(r.source, r.page) for r in result.sources] == [("used.pdf", None)]
    unknown = RAGTool._source_references([Document(page_content="x", metadata={"page": 2})])
    assert unknown[0].source is None and unknown[0].page == 3


def test_empty_retrieval_never_invokes_generation():
    from langchain_core.language_models.fake import FakeListLLM
    from langchain_core.callbacks import BaseCallbackHandler
    from intellectaengine.tools.rag_tool import RAGTool

    class NoGeneration(BaseCallbackHandler):
        raise_error = True

        def on_llm_start(self, *args, **kwargs):
            pytest.fail("Empty retrieval must not generate an answer")

    store = SimpleNamespace(as_retriever=lambda **_: SimpleNamespace(invoke=lambda q: []))
    result = RAGTool.run(
        "q",
        store,
        FakeListLLM(responses=["unsupported"], callbacks=[NoGeneration()]),
        return_result=True,
    )
    assert not result.sources and "could not find" in result.answer.lower()

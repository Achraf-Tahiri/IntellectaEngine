# Reproducible examples

These examples contain no private documents or credentials. The Lumen Library
brief is original, entirely fictional content under the project's [MIT license](../LICENSE).
Chinook is the existing reviewed fixture; its attribution and checksum remain in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Queries use aggregate sales and
catalogue data, not sample customer contact fields.

## PDF reference answers

Upload [field-notes.pdf](field-notes.pdf) and click **Process PDFs** before choosing
**Force: RAG Documents**. A working LLM and embedding model are required for live
answers. These facts are reference answers checked against extracted source text,
**not evidence that a live LLM produced them**. Page numbers below are one-based.

| Question | Expected source facts | Page |
| --- | --- | --- |
| How many kits are in the pilot, and of which types? | 24: 10 drawing, 8 puzzle, 6 building. | 1 |
| When does the pilot run, and how long is a loan? | 5 April–16 May 2027; seven days per loan. | 1 |
| How many week-three returns were on time? | 33 of 36; three were late. | 2 |
| What changed at the review, and when is the next one? | Added a checkout contents checklist; kept seven-day loans; next review 3 May 2027. | 2 |
| What is the pilot's total budget? | Intentionally absent. Say the documents do not supply a budget; do not invent an amount. | 2 explicitly states the omission |

Editable source: [field-notes.txt](field-notes.txt). A line containing `---`
separates pages. Headings and paragraphs remain plain text.

## Regenerate the PDF

The authoring-only [generator](../scripts/generate_example_pdf.py) uses ReportLab
4.4.9, standard PDF fonts, deterministic metadata (`invariant=1`), fixed page
breaks, and layout bounds. It adds no application dependency. From the checkout,
use a separate disposable environment with Python 3.12:

```bash
python3.12 -m venv /tmp/intellecta-pdf-authoring
/tmp/intellecta-pdf-authoring/bin/python -m pip install 'reportlab==4.4.9'
/tmp/intellecta-pdf-authoring/bin/python scripts/generate_example_pdf.py
sha256sum examples/field-notes.pdf
pdftoppm -scale-to 1200 -png examples/field-notes.pdf /tmp/intellecta-page
uv run --frozen pytest tests/integration/test_examples.py
```

Installing authoring tools requires network access unless cached. Repeated runs
with the same source, Python, and ReportLab version produce identical PDF bytes.
Inspect **both rendered pages** after editing. The regression test runs the real
`DocumentIngestionService`, extraction/chunking, and temporary Chroma insertion
with deterministic fake embeddings, then checks source text and page metadata.
It evaluates fixture ingestion, not semantic retrieval or answer quality.

## Chinook analytical references

[chinook-queries.json](chinook-queries.json) contains each natural-language question,
exact SQL, and expected `SQLitePolicy.query` output. The bundled database is never
modified. All statements pass through the existing `USE_SAMPLE_DB` read-only
policy, including its normal work/result limits.

| Question | Verified reference result |
| --- | --- |
| How many invoices, and what is their total value? | 412 invoices; 2328.60 in the database's monetary units. |
| Which three billing countries have the highest invoice totals? | USA 523.06; Canada 303.96; France 195.10. |
| Which three genres contain the most tracks? | Rock 1297; Latin 579; Metal 374. |

The JSON preserves the policy's string formatting (for example `2328.6`). No
currency conversion, model-generated SQL accuracy, or live inference is implied.
Run the test command above to recheck all three statements without a provider.

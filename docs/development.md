# Development baseline

Phases 1–6 establish repeatable installation, offline checks, isolated
session-owned conversation history, unified dispatch/configuration/failure
contracts, PDF replacement, bounded read-only SQLite execution, and bounded web evidence.
Phase 7 adds an installable package and distribution checks without changing these contracts.
Phase 8 adds a local Docker workflow and isolated container verification.
Phase 9 adds concise project/architecture documentation, original reproducible
examples, and authentic browser captures. Start with [the README](../README.md),
[architecture](architecture.md), or [demo instructions](demo.md).

## Environment and dependencies

The initial supported runtime is CPython 3.12 on Linux. `.python-version` and
`pyproject.toml` declare that boundary. Windows/macOS are not yet CI targets.

Use uv 0.12.2:

```bash
uv sync --locked
uv run --frozen intellectaengine
# Compatibility: uv run --frozen streamlit run app.py
uv run --frozen python -m pip check
uv run --frozen ruff check .
uv run --frozen ruff check tests --select E4,E7,E9,F
uv run --frozen ruff format --check tests
uv run --frozen pytest
uv build
uv run --frozen python scripts/check_distribution.py
```

`pyproject.toml` declares direct dependencies; `uv.lock` fixes their complete
resolution. `requirements.txt` is the generated runtime export;
`requirements-dev.txt` includes runtime and development tools. For pip users in
an activated Python 3.12 environment:

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m pip install --no-deps -e .
python -m pip check
python -m pytest
```

The requirements files are dependency exports, not application installations. The
additional `pip install --no-deps -e .` installs the application and its launcher;
use `python -m pip install --no-deps dist/intellectaengine-0.1.0-py3-none-any.whl`
for a built release. Build isolation installs the pinned setuptools backend.
For runtime-only setup use `uv sync --locked --no-dev` (or `requirements.txt`
followed by the same project-install step). `uv sync` installs the project editable.

Linux and Windows resolve PyTorch from its explicit public CPU index. This avoids
installing a CUDA stack for the baseline. Requirements exports cannot express
per-package index selection, so they emit that index globally and pin distribution
hashes. Prefer `uv sync --locked` for the exact index policy.

No embedding weights are included. Creating an embedding model for the first time
may download weights; the test suite does not create real embedding models.
Chroma brings some infrastructure-named packages transitively; the application
does not deploy or use a Kubernetes cluster.

The existing Gemini 2.1.11 integration is retained in this phase.
Dependency resolution and import success are not a live-provider compatibility
guarantee. Unused direct requirements for `langchain`, `langchainhub`, `validators`,
and `pandas` were removed; a package may still appear transitively in the lock.
`langchain-classic` and `torch` are now explicit because application code imports them.
Sentence Transformers was updated to permit patched Transformers releases; see
[the advisory review](dependency-security.md) for remediation and scoped exceptions.

### Updating dependencies

Edit direct constraints in `pyproject.toml`, then resolve and check them:

```bash
uv lock
uv sync --locked
uv export --frozen --no-dev --no-emit-project --emit-index-url --output-file requirements.txt > /dev/null
uv export --frozen --no-emit-project --emit-index-url --output-file requirements-dev.txt > /dev/null
uv run --frozen python -m pip check
uv run --frozen ruff check .
uv run --frozen ruff check tests --select E4,E7,E9,F
uv run --frozen ruff format --check tests
uv run --frozen pytest
uv run --frozen pip-audit --local
```

On PowerShell, replace `> /dev/null` with `> $null`. To deliberately upgrade a
locked package, use `uv lock --upgrade-package PACKAGE` before syncing. Review
the lockfile and generated exports together; do not edit exports manually.

## Tests and CI

The baseline suite covers:

- Configuration defaults, environment overrides, validation, and example completeness.
- Ignore rules and the reviewed sample database checksum.
- Tracked ignored files, when Git metadata is available.
- Full application imports and the initial Streamlit screen.
- Session isolation, full UUIDs, clear/reset/undo, bounded model history, and cleanup.
- Actual Streamlit chat and sidebar actions with fake providers/tools in every mode.
- A real ReAct executor using a scripted model, including intermediate tool calls
  and failures, with exactly one final user/assistant pair committed per submission.
- Headless dispatch in every mode, resource/provider ordering, safe failures,
  local prompt construction, exhaustion, and malformed or unavailable actions.
- Real SQL toolkit calls against Chinook with scripted tool-calling chat models.
- Environment-configured UI defaults, custom models, provider switching, and reset.
- Real temporary Chroma collections: failed embedding/retry, collision ownership,
  completion manifests, deletion verification, and clear/reset UI failures.
- Bounded PDF reads, page attempts and chunk production; encrypted and partial PDFs;
  request-local evidence across real scripted ReAct calls and prompt context budgets.

An autouse fixture changes to a temporary working directory before application
imports and clears relevant environment overrides. This prevents reading the
developer's `.env`. `pytest-socket` blocks network sockets; Hugging Face offline
flags prevent accidental model downloads. Unix sockets are allowed for the
Streamlit test harness's local asyncio event loop; Internet sockets remain blocked.
Tests must not import application
configuration at test-module collection time, before this fixture runs.

The GitHub workflow installs the lock, checks requirements export drift, runs
`pip check`, Ruff, tests, wheel/sdist validation, and a dependency advisory audit. It needs no application
API keys. Package installation and advisory lookup need network access; application
tests do not. Third-party actions are pinned to commit SHAs with read-only repository
permissions. The audit reports known published advisories, not proof of safety.
The unfiltered local audit above reports known Chroma server advisories. CI excludes
four reviewed server-only advisory aliases because this application uses embedded
Chroma, and audits the base PyTorch release separately. The exact scope and rerun
instructions are in [dependency-security.md](dependency-security.md).

Ruff initially checks critical syntax/control-flow/undefined-name errors in legacy
code. New tests receive broader lint and formatting checks. Expanding lint across
the whole application belongs to the later cleanup phase.

## Publication hygiene

Keep `.env`, uploaded documents, vector stores, logs, model caches, and private
exports outside version control. `.env.example` must contain blank credential
fields. The approved sample database is the only database exception in `.gitignore`;
its provenance and redistribution notice are in `THIRD_PARTY_NOTICES.md`.

The initial audit found an empty `.git` directory. The owner confirms this project
has never been committed or pushed, so there is no prior project Git history to
migrate. The [first-repository preparation](release-readiness.md#first-local-repository-preparation)
records the reviewed initial index and executed Git-metadata test. External
credential exposure remains unknown. Before publishing:

1. Inspect tracked files and run the baseline publication tests.
2. Scan the complete Git history with a secret scanner; checking `.gitignore`
   alone does not remove previously committed secrets.
3. Revoke/rotate any credential that has been committed or otherwise exposed.
4. Review screenshots and example documents for personal information.

The local private `.env` is intentionally not modified by this phase. No automated
test reads it or prints credential values. Nothing is committed or pushed by the
baseline setup.

## Conversation ownership and lifecycle (Phase 2)

Each Streamlit session owns its transcript and a separate `MemoryStore` instance.
Defaults are copied per session and session IDs use full UUID4 values. There is
no process-wide conversation registry, shared default session, or disk persistence
for chat. The ID is diagnostic context, not an authentication mechanism.

`ChatInterface` commits a complete question/final-reply pair through
`SessionStateManager.complete_turn` exactly once after dispatch. Automatic routing,
forced RAG/SQL/web/chat, and the no-tools fallback use this same boundary.
`RouterAgent`, `AgentExecutor`, and `ChatTool` never save history. Internal tool
queries, observations, and intermediate replies are not conversation turns.
Standalone callers must own and update their `MemoryStore` explicitly; an
`AgentContext` without a supplied memory gets a fresh, independent instance.

The model window stores at most **10 complete turns** (20 messages); history
reads return detached copies. This is a turn limit, not a token or byte limit.
The visible transcript remains available for the lifetime of the session. Undo
removes its latest complete pair and rebuilds the model window, restoring the
next older turn if needed. Clear erases both histories but keeps the session ID
and configuration. Reset clears the old memory object before replacing session
state and generating a new ID. Sidebar actions run as callbacks before widgets
are recreated. Clear chat leaves PDFs intact; the sidebar's full Reset first verifies
PDF collection deletion, then invokes the state reset. Failed cleanup preserves the
session references and displays an error (see Phase 4 below).

**Failure policy:** a handled failure records the question and the exact error
reply displayed to the user as one turn, just like a successful reply. Typed tool failures and missing-resource guidance follow this same policy.
Undo removes a failed turn in the same way as a successful one. If execution is
interrupted before there is a final reply, no turn is committed. There are no
automatic retries or durable exactly-once guarantees across process crashes.

History is passed to automatic routing and direct chat. Forced RAG/SQL/web still
receive their current query only, but their final replies become history for the
next router/chat request. Rewriting follow-up queries for those tools is outside
this phase. The maintained local ReAct prompt retains `tools`, `tool_names`, and
`agent_scratchpad`; offline executor tests exercise real routing.

Memory lifetime follows Streamlit session-state lifetime. Once Streamlit releases
a disconnected session, there is no global registry retaining its conversation;
release timing is controlled by Streamlit, not an application idle-time timer.
Reset explicitly clears the old store even if a caller still holds a reference.
The current UI serializes requests within each session; background or overlapping
requests would require additional coordination. This is not a multi-user hosting
or authentication guarantee.

## Application and failure boundary (Phase 3)

`intellectaengine.core.application.ApplicationService.run()` is the synchronous, Streamlit-independent
entry point for `auto`, `rag`, `sql`, `web`, and `chat`. It accepts an `AgentContext`
and returns an `AgentResult` with `answer`, `tool_used`, `error` (an `ErrorCode` or
`None`), and an `ok` property. `AgentContext` and `AgentResult` live in
`src/intellectaengine/core/contracts.py`; imports through
`intellectaengine.core.router_agent` remain supported.
Import concrete core modules directly; the eager package exports were removed to
break the tool/router import cycle. Phase 7 applies this rule to every package initializer.

The UI builds context, renders the result, and calls `complete_turn()` once.
The service, router, and tools never write conversation history. Headless callers
own persistence; repeated calls do not commit turns. RAG no longer creates an
unused, separate chain memory. History behavior and failure undo remain as in
Phase 2. `KeyboardInterrupt` and other `BaseException` interruptions propagate
without a final result or UI commit.

Successful tool calls return strings. Failed calls raise `ApplicationError`;
LangChain adapters let those exceptions propagate, and the service/router convert
them to the shared result. There is no emoji/prefix parsing. Codes distinguish:

| Code | Meaning |
| --- | --- |
| `missing_resource` | PDFs/database configuration or the bundled database file is missing. |
| `invalid_configuration` | Unsupported mode/provider, blank query/model, or missing selected-provider credentials. |
| `unsupported_capability` | A required local model interface is unavailable or reports `NotImplementedError`. |
| `provider_failure` | Provider construction or direct chat inference failed. |
| `tool_failure` | Retrieval, database, or web execution failed; also an unavailable tool action. |
| `execution_failure` | Router construction/invocation, malformed ReAct output, or missing/empty answer failed. |
| `execution_limit` | The router, nested SQL executor, SQLite VM, or schema inventory exhausted its budget. |

Errors inside compound RAG/SQL operations are classified at the tool boundary;
unknown router invocation errors are classified as execution failures. These codes
do not attempt to infer provider-specific HTTP status or retryability from text.

Automatic routing is **fail-fast**: any tool failure terminates the request.
It cannot become an ordinary observation followed by a misleading success answer.
There is no automatic repair, retry, provider switch, or continuation after a
parser error. Tools requiring absent resources are omitted from automatic routing;
a request for an unavailable tool fails. A model can still answer directly without
using a tool; routing accuracy is not guaranteed.

The prompt is local in `src/intellectaengine/core/prompts.py`; there is no Hub pull. Both executors
allow six iterations and a 60-second elapsed-time budget checked between steps.
The synchronous budget does **not** interrupt a blocking provider/network call.
`src/intellectaengine/core/execution.py` adapts the locked LangChain executor's protected synchronous
hooks to report limits and invalid tool actions explicitly. Recheck these hooks
when upgrading LangChain. Web reading has separate byte, observation, timeout and between-read elapsed limits (Phase 6).

Public failure messages and application failure logs use allowlisted guidance
and category codes. Arbitrary exception payloads are discarded rather than
filtered with a secret regex. Queries, observations, driver/SDK exception text,
credentials, and database URIs are not included in these failure results. The
UI developer panel shows a failure code instead of raw intermediate steps, and
router verbosity stays off. Synthetic-secret tests exercise these boundaries.
This is not a general content redactor: successful model/tool output and the user's
own transcript may contain sensitive content. Application PDF/index failures also
discard raw exception text; third-party tracing/logging is outside this guarantee.

## PDF ingestion, retrieval, and index lifecycle (Phase 4)

Processing a selected upload batch is explicit **replace-on-success**, not append.
The headless ingestion service reports safe per-file outcomes: `success`, `partial`,
`empty`, `unreadable`, `limit_exceeded`, and `duplicate`. Exact duplicate bytes in a
batch are indexed once and retain the first safe display name. A batch containing
usable text can succeed with a partial report; a batch with no usable text or an
indexing failure leaves the prior active collection and inventory untouched.

Chunks have deterministic content/page/chunk IDs. Collection compatibility binds the
session ID, content hashes, embedding provider and resolved model, splitter size and
overlap, plus a format marker. Reprocessing identical content/configuration reopens
without appending chunks or re-embedding. A renamed identical upload retains the
active index's original display name. Reopen requires the explicit `DocumentSet`
handle and matching session/configuration; it never discovers another session's index.

Creation uses Chroma's exclusive `create_collection` API, initially marked `building`.
Only after insertion and verification of the expected chunk count and a SHA-256
manifest of sorted chunk IDs is it marked `ready`. Reopen checks that marker, count,
ID manifest, and the handle's inventory count before returning a store. These checks
detect incomplete insertion and missing/replaced IDs; they are not an authenticity
check against someone who can edit local storage.

An ordinary creation failure retains its extraction report and attempts cleanup of
only the collection ID owned by that invocation. The old active index is untouched;
after successful cleanup the same batch can be retried. A pre-existing name collision,
whether valid or incomplete, is neither deleted nor adopted by replacement. Cleanup
failure, interruption, or an uncertain creation response can leave an inactive index
that blocks that deterministic name. There is no automatic crash recovery: retain the
prior active handle, inspect the explicit leftover before using the supported deletion
API, or reindex in a fresh session. A process kill can also interrupt publication or old
index cleanup. No durable transaction or concurrent-writer guarantee is claimed.

The corrected format is `intellectaengine-document-set-v2`. Earlier indexes lack the
completion manifest or use the earlier splitter algorithm; reopen rejects them. Reindex
from the original PDFs. Existing user indexes are never automatically migrated/deleted.

Configured limits bound bytes per upload, files, attempted page extractions, produced
chunks, and retrieved-context characters. Reads request at most the remaining byte
allowance plus one overflow sentinel; seekable upload positions are restored. Once a
PDF's page count is known, a file exceeding the remaining page budget is rejected
before any `extract_text` call. Empty and failed page attempts consume budget. Files
rejected before extraction consume no page budget; later files can use what remains.

Pages are extracted and split in sequence. The existing recursive splitter operates
on windows of at most four configured chunk sizes, with configured overlap between
windows. It only materializes a bounded window's intermediate strings. Chunk Documents
stop at the remaining budget, and later pages/files are not extracted after exhaustion.
Window edges can change chunk boundaries, which is why the format was revised. Explicit
zero overlap is retained. A file exceeding a resource budget is wholly omitted; other
successful files can still replace the batch, with skipped outcomes reported. Page
errors retain the readable pages as `partial`.

Report `pages` counts attempted extractions (including empty/failed/discarded pages);
`chunks` counts retained chunks and equals the sum of per-file chunk counts.
`produced_chunks` also counts discarded chunks and enforces the work budget across
files. Discarding a file never refunds work already performed. Exhausted budgets may
conservatively skip later empty pages/files without reading them.

These safeguards do not sandbox an arbitrarily expensive in-process PDF parser or
bound the parser's decompressed page allocation. Original upload bytes are not
persisted; display filenames are sanitized and never form paths. Embedded Chroma uses validated collection APIs, not
raw directory deletion, and collection names cannot escape the configured root.

Clear deletes and verifies removal of the active collection before it clears UI state.
Only `chromadb.errors.NotFoundError` from collection lookup establishes absence.
Client initialization, lookup, deletion, or verification errors return failure; an
unverified deletion never produces a success toast. Reset uses the same policy,
retaining the handle on failure. If deletion succeeded but verification failed, the
retained handle may already be unusable; retry cleanup when storage is available.
Interrupted processes can leave inactive collections; there is no saved-library UI or automatic
garbage collection. Chroma deletion is not secure-erasure assurance for SQLite pages,
backups, or storage media.

MMR retrieval is retained. `RAG_CONTEXT_CHAR_LIMIT` bounds the entire inserted
`{context}` string, including source/page labels and the two-newline separators
between excerpts. It excludes the surrounding instructions, question, and any model
history; it is not an exact token budget. Tests measure that string in the actual
generation prompt. Context labels source/page (one-based) where metadata is
available. Structured retrieved references survive forced and automatic routing and
are not dependent on Markdown copied by the model. They identify retrieved context,
not verified claim-level support or answerability; missing source/page metadata is
never manufactured. Only excerpts that fit and are supplied to generation produce
references. An empty result returns explicit no-text guidance without generation.
Each router invocation owns its evidence list; multiple successful RAG calls aggregate
and deduplicate within that request. Neither success nor failure stores evidence in
caller-owned `AgentContext.extra`, so reused contexts cannot inherit prior references.

## Configuration and provider capabilities (Phase 3)

New sessions and full resets use validated `AppSettings` for the LLM provider,
its configured model, and embedding provider. Settings are loaded at process
startup, so restart after editing the environment. Normal reruns preserve user
selections. A provider-change callback sets that provider's configured default
before model widget creation; switching back also restores its default, not a
previous custom override. The model field accepts arbitrary nonblank identifiers.
Catalogue entries are suggestions in code, not a compatibility allowlist.

Factories accept an optional `config=AppSettings(...)`; session initialization and
reset also accept settings for tests. The application/router accept an optional
`llm_factory` callable. These are small injection points, with no container or
framework. Tests import configuration only after the isolation fixture runs.

Provider clients are created only when needed: forced web does not construct an
LLM or require its credentials/model. Forced RAG/SQL check resource presence first;
SQL validates its SQLite URI and approved existing path before provider creation. Automatic mode needs an LLM to route.
Factories validate the chosen provider and its required credentials before SDK
construction. They never fall back to a different provider. Installing the locked
Ollama integration does not install a server or download an Ollama model.

Text ReAct does not require native model tool calling, but the chosen model must
follow its format and support the integration's generation options. SQL uses
LangChain's `tool-calling` agent and checks local tool binding support. Gemini,
Groq, OpenAI, and Ollama remain selectable; a common `BaseChatModel` does not prove
that every model supports SQL tools, stop sequences, or a requested temperature.
Successful binding is only a local check; server-side model capabilities remain
unverified without live-provider tests. No such tests or paid calls are made here.

The SQL toolkit uses throwing database methods instead of LangChain's error-string
helpers; SQL/schema errors terminate the request. Scripted chat models exercise the
real toolkit against Chinook, including failure propagation and iteration limits.
Phase 5 adds native SQLite authorization and bounds, described below. Remote
database safety and broader provider compatibility remain later work. Real-model retrieval quality, async/streaming, and deployment are unchanged in scope.
The package migration is described in Phase 7 below.

## SQL policy and lifecycle (Phase 5)

`src/intellectaengine/core/sql_policy.py` owns parsing, filesystem approval, connection construction,
introspection, authorization, and result/work budgets. SQLAlchemy's structured
`make_url` parser is retained, but SQLAlchemy engines/pools are no longer created
by the SQL connector or tool. Every operation owns a fresh native SQLite connection
and closes it in `finally`, including setup, introspection, execution, model-related
failure paths and interruptions. No live connection is retained during model calls
or stored in UI state, so there are no owned engines to dispose or reused handles
with disabled safeguards/stale budgets. The sidebar stores connection metadata;
it does not promise that a file remains available after validation.

Supported inputs are `USE_SAMPLE_DB` and absolute file URIs of the form
`sqlite:////absolute/path/data.db` or `sqlite+pysqlite:////absolute/path/data.db`.
The sample works without custom configuration. Custom files require an explicit
`SQL_ALLOWED_ROOTS` JSON array of absolute directories, default `[]`. All resolved
roots must exist; use only directories controlled by the operator. Paths are
resolved with `Path.resolve(strict=True)` and confined using `is_relative_to`,
including symlinks and `..`; similarly named sibling directories are not approved.
Symlinks into an approved directory are accepted, escaping symlinks rejected.
The file must be an existing regular file. Missing files cannot be created by
read-only opens. Relative paths, memory databases, SQLite `file:` URIs, credentials,
hosts, query parameters (including `mode`/`uri`), fragments and other dialects fail
before a connection opens. Literal spaces and percent characters in paths are
preserved and safely encoded into the internally constructed SQLite file URI.

Each connection uses `mode=ro`, disabled extension loading, `query_only=ON`,
`trusted_schema=OFF`, memory-only temporary storage, and an authorizer that permits only reads, SELECT/recursive
operations, and a reviewed set of analytical/scalar functions. Writes, schema
changes, temporary tables, ATTACH/DETACH, transactions, user PRAGMAs, table-valued
PRAGMAs, and extension/file functions are denied. Python's native `execute`
rejects multiple statements; prompts and the query checker are not enforcement.
Some otherwise read-only functions outside the allowlist are deliberately unsupported.
Ordinary joins, aggregates, window functions, and read-only CTEs are supported.
SQLite version-dependent functions still depend on the local SQLite build.

Trusted introspection uses a fixed parameter-free `sqlite_schema` read through
these same protections. It needs no general PRAGMA exemption. No sample rows are
included; querying data is explicit. Empty schemas are valid, but corrupt,
unavailable or oversized schema inventories raise safe failures rather than
becoming successful empty schemas. UI publication happens only after discovery
succeeds; a failed replacement retains the previous URI, connected flag and table
inventory. The URI input is masked. Exceptions and failure logs never include
URIs, SQL, results, or raw driver/provider messages. Successful output and model
tracing remain outside that failure-message guarantee.

`PolicySQLDatabase` implements the public database surface used by the locked
LangChain toolkit without an engine-backed execution escape. Query and schema
methods propagate typed failures, including their misleadingly named `no_throw`
compatibility methods. `BoundedSQLToolkit` caps all tool observations (query,
schema, list, checker) and preserves fail-fast exceptions. Actual tool-calling
agents and the outer ReAct router remain in use. Forced and automatic SQL both
commit exactly one final question/reply pair at the existing UI boundary; failed
turns remain undoable. No dependency or provider interface was replaced.

| Limit | Default and validation | What it bounds |
| --- | --- | --- |
| `SQL_TOP_K` | 10, 1–1000 | Returned rows per statement; incremental fetch, at most one extra overflow row. A call override can only lower it. |
| `SQL_CELL_CHAR_LIMIT` | 1000, 32–100000 | Characters in each rendered query cell, including its truncation marker. |
| `SQL_OBSERVATION_CHAR_LIMIT` | 12000, 128–100000 | Each complete toolkit observation, including formatting and markers; also the schema inventory budget, which fails if exceeded. |
| `SQL_STATEMENT_SECONDS` | 2.0, >0 to 30, finite | Elapsed deadline tested by SQLite's progress callback. |
| `SQL_STATEMENT_STEPS` | 1000000, 1000–100000000 | Approximate VM instruction budget, checked in increments of 1000. |
| `SQL_LOCK_TIMEOUT_MS` | 250, 1–5000 | SQLite busy/lock wait timeout, separately from VM progress. |

The progress budget covers execution and fetching on that connection; every new
operation gets a fresh budget. A native interruption becomes `execution_limit`;
lock contention and other execution errors are `tool_failure`. Result truncation
is successful and marked `[truncated]`; over-budget work is a failure. A fixed
SQLite length limit of 1,000,000 bytes bounds native string/blob/encoded-row sizes,
and SQL text is limited to 100,000 bytes. Exceeding these native limits fails
rather than returning an oversized value. These are not a total process-memory
budget: SQLite may allocate intermediate structures, and a fetched cell is
materialized before its displayed representation is shortened.

Observation budgets count characters, not tokens, and apply per tool call. They
exclude model-generated SQL arguments, surrounding prompts, history and the outer
router's final answer. The SQL subagent's reply is capped too, because it becomes
an observation in automatic routing; the existing six-iteration/60-second
between-step agent limits remain.
The progress callback can interrupt expensive SQLite VM work, but cannot guarantee
hard wall-clock interruption of every filesystem operation, native function or
provider call. Lock waits have their own timeout. This is defense against generated
SQL in a local personal project, not enterprise row/table authorization or a sandbox
for hostile local processes, malicious database files, path replacement races,
hard links, or untrusted native extensions installed by other application code.
SQLite can read its own journal/WAL sidecars. Operators must control the filesystem
and approve data suitable for the configured model provider. Remote PostgreSQL/MySQL
support requires dialect-specific controls and real boundary tests before returning.

Regression tests use disposable SQLite files for all destructive probes, native
authorization/progress handlers, tracked real connections, scripted chat models,
and actual LangChain/Streamlit boundaries. The sample is queried read-only only.
No external database, paid model, download, or live application research is used.
Phase 5 validation: **227 passed, 1 skipped** (unavailable Git metadata), with the
existing LangChain Community deprecation warning. Locked synchronization, dependency
consistency, both documented Ruff checks, test formatting, and runtime/development
export comparisons passed. Export comparisons used temporary files and excluded
only the generated command header; dependencies, lockfile, committed export files
and advisory exceptions remain unchanged.
Web hardening follows in Phase 6 below. Packaging, Docker, async/streaming and
deployment remain outside these phases.

## Web search and Jina Reader (Phase 6)

`src/intellectaengine/tools/web_research_tool.py` keeps keyword search through DuckDuckGo and the
`SCRAPE:<url>` interface through Jina. `src/intellectaengine/core/web_policy.py` contains the small
headless URL/display policy. No origin fetch, DNS lookup, browser, custom proxy,
alternative provider, application retry or fallback was added. Forced web still
runs before LLM construction. Existing service/router/UI ownership is unchanged:
one final reply per submission, safe typed failures, failure undo, and no commit
on interruption. The automatic executor stops immediately on web failure.

### Inputs and the two network boundaries

Direct `run`, `search`, `scrape`, and structured inputs validate before creating
clients. Queries must be nonblank bounded strings without control/format
characters; whitespace around them is trimmed. The URL policy uses `urlsplit`
and `ipaddress`, accepts absolute HTTP(S), IDNA hostnames, ordinary public IPv4
and IPv6 literals, and only omitted ports or the scheme's exact default (`80`
for HTTP, `443` for HTTPS). Credentials, whitespace/control characters,
backslashes, percent-encoded authorities, trailing dots, empty/padded/nondefault
ports, malformed brackets, single-label names and local/internal suffixes fail.
Reserved local suffixes include localhost, localdomain, local, internal,
intranet, lan, home, corp, private, arpa, test, invalid and onion.

Non-global, multicast, reserved and deprecated site-local IPv6 literal IPs fail. All IPv4-mapped IPv6 and 6to4/Teredo
forms are conservatively rejected, including mapped public addresses. Integer,
short, octal, hex and padded IPv4 forms are rejected rather than interpreted;
a numeric/hex final hostname label is not treated as a DNS name. Scheme/host
normalization preserves path/query escaping and order; malformed percent escapes
fail. IDNA expansion must also fit the URL limit. Rejected URLs are neither
sent to Jina nor printed in failure messages.

The application connects to **HTTPS r.jina.ai**, with the target URL embedded in
the reader request. Jina makes the separate origin request. Valid target URLs,
**including their query strings**, are disclosed to Jina; HTTP fragments are
client-side and are not transmitted by Requests. Search queries are disclosed to
DuckDuckGo. Do not submit private tokens in URLs/queries. Lexical checks cannot
establish what Jina resolves, whether a public-looking name resolves privately,
or where Jina follows origin redirects. There is no complete SSRF prevention,
DNS-rebinding protection or public-host reachability guarantee.

### Reader transport and resource policy

Each read owns a fresh Requests session and response, closed through context
managers on success, typed failure, truncation and `BaseException` interruption.
`trust_env=False` prevents `.netrc` authentication, environment proxy selection
and environment CA overrides. No local cookie jar or credentials are loaded.
Default Requests certificate verification remains enabled. There is an honest
`IntellectaEngine` User-Agent, with no browser/bot-bypass claim. Only one reader
request is attempted; Requests' default adapter has zero retries.

Endpoint redirects are disabled and all non-2xx statuses fail. A response hook
rejects and closes errors/redirects before Requests can prepare `Response.next`:
the locked implementation otherwise consumes a redirect body even with
`allow_redirects=False`. This does not disable redirects followed internally by
Jina while fetching an origin page.

Reads use bounded `response.raw.read(..., decode_content=False)` calls, at most
8 KiB each and at most the byte allowance plus one overflow sentinel overall.
The cap does not trust `Content-Length`; absent, excessive or misleading headers
cannot increase it. HTTP framing is still owned by Requests/urllib3: premature
closure/framing errors fail, and a falsely short framing length can end a response
early without application-level proof that origin content was complete.
No `.text`, `.content`, guessed-encoding scan or whole-response decompression is
used. `Accept-Encoding: identity` is requested, and any other Content-Encoding
is rejected before reads. This avoids an application decompression-bomb path;
these byte limits are not a total network/TLS/header/process-memory budget.

Accepted MIME types are text/plain, text/markdown, text/html and
application/xhtml+xml. A Content-Type is required. UTF-8 is the default; explicit
UTF-8, ASCII, ISO-8859-1 and Windows-1252 are supported with strict decoding.
Unknown encodings, invalid sequences, empty/whitespace-only text and binary
control bytes fail. A truncated multibyte tail is discarded, without interpreting
it as malformed full content. MIME labels do not prove that arbitrary printable
content is meaningful text. HTML/Markdown is displayed as escaped evidence,
not executed or rendered as provider-supplied images/links.

Timeouts apply to connection and idle reads; the elapsed deadline starts before
session creation and is checked before and after every body read. A blocking DNS,
TLS or read operation is **not** forcibly cancelled at that deadline. Trickle
responses and underlying blocking operations can exceed it. The synchronous
router's separate between-step budget remains unchanged.

### Search and display policy

The locked DDGS constructor receives `timeout` and `verify=True`; `text` receives
`max_results` and `backend="html"`, avoiding its automatic html/lite fallback.
Application consumption uses `islice` and inspects at most the requested count,
including malformed entries. It never scans extra entries to fill missing slots.
The installed `DDGS.__exit__` is a no-op, so the application also enters/exits its
owned `primp.Client` context explicitly on success, failure and interruption.
Recheck this interface when changing dependencies.

DDGS returns a materialized list and controls HTTP response buffering, pacing,
HTML parsing, cookie handling and pagination internally (up to five HTML page
requests in this lock). Its result/request timeout controls do not provide our
Jina byte or elapsed-time budgets. DDGS retains its installed proxy behavior,
including `DDGS_PROXY`; the Jina `trust_env=False` policy is specific to Requests.
DDGS/primp internally selects browser impersonation; the application makes no
claim that this bypasses bot controls. Application code adds no retries/fallbacks.

Missing title/body fields default to empty strings; at least one must contain
text in its bounded prefix. Wrong types, malformed entries and links rejected by
the target policy are skipped. An actually empty iterable is a successful
no-results observation. A nonempty batch with no usable entries, invalid top-level
response, iterator error or provider exception is a typed failure. Mixed batches
report omitted entries. Valid URLs are separately encoded into fixed-label
clickable Source links; overlong displayed links are omitted whole. Titles and
snippets are escaped literal text, not arbitrary Markdown links/images.

Complete search observations include only whole result blocks that fit and mark
omitted tail content. Page observations budget headings, source links and body
together. `[truncated]` markers are included inside the character cap; byte overflow
is also explicitly marked. Observations are characters, not tokens; these limits
exclude surrounding prompts/history and the router's model-generated final reply.
Tool descriptions and the local router prompt treat web evidence as untrusted
and discourage following embedded instructions, without claiming injection immunity.

Failure messages use existing allowlisted `tool_failure` guidance and never include
queries, URLs, page bodies, credentials or arbitrary exception text. DDGS's known
raw-exception diagnostic logger is sanitized, as are urllib3 connection-pool
request diagnostics for the fixed reader host. Successful observations/transcripts
and external tracing, callbacks, native-library diagnostics or operator-added
logging are not a general content-redaction boundary.

### Configuration

All values load through validated `AppSettings`; restart after changes. `None`
means use the configured cap for method overrides. `max_results`, `max_chars`
and `timeout` overrides must be integers (not booleans), positive, within the
configured maximum; `max_chars` is at least 128. Zero, negative, wrong-type and
above-cap overrides fail before transport, rather than disabling a limit.

| Setting | Default; allowed range | Meaning |
| --- | --- | --- |
| `WEB_SEARCH_MAX_RESULTS` | 5; 1–20 | Requested and inspected search result count. |
| `WEB_QUERY_CHAR_LIMIT` | 1000; 1–10000 | Search query characters before trimming. |
| `WEB_URL_CHAR_LIMIT` | 2048; 128–8192 | Target URL characters, including path/query; excludes SCRAPE prefix. |
| `WEB_OBSERVATION_CHAR_LIMIT` | 6000; 128–100000 | Entire successful observation including markers/formatting. |
| `WEB_RESPONSE_BYTE_LIMIT` | 262144; 1–2000000 | Retained identity-encoded page bytes; one extra byte detects overflow. |
| `WEB_SCRAPE_TIMEOUT` | 15; integer 1–60 seconds | Jina read timeout; connect is min(5, value). Also DDGS request timeout. |
| `WEB_ELAPSED_SECONDS` | 30; finite >0–120 seconds | Jina deadline checked around each body read. |

Fixed display sublimits are 240 characters per title, 1000 per snippet, and 800
characters per encoded source URL (excluding its fixed link wrapper). They need
no separate settings. Body display escaping and markers consume the same budget.

Tests use fake search clients and real Requests sessions/responses with fake
adapters and bounded urllib3 response streams. Real structured tools, ReAct and
Streamlit exercise success/failure, safe diagnostics, cleanup and exactly-once
history/undo. Internet sockets remain blocked; no real searches/pages or paid
providers are used. Dependencies, lockfile, exports and advisory exceptions are
unchanged in Phase 6. Packaging is covered in Phase 7 below; Docker, asynchronous
UI work and deployment remain later work.

Phase 6 validation: **388 passed, 1 skipped** (unavailable Git metadata), with the
existing LangChain Community deprecation warning. `uv sync --locked`, dependency
consistency, both documented Ruff checks, test formatting and the full offline
suite passed. Runtime/development exports matched temporary locked exports after
excluding only the generated command header; committed exports were not rewritten.
No required check was left unrun. Live-service behavior remains unverified by design.

## Installable package and developer workflow (Phase 7)

Application code lives in `src/intellectaengine/`, with the existing `config`,
`core`, `connectors`, `tools`, and `ui` modules and filenames. Import concrete
modules using the `intellectaengine` prefix; the old generic top-level packages
are removed. Package initializers have no provider, settings, or UI side effects.
Importing `intellectaengine.core.application` remains independent of Streamlit.
No source-root `pythonpath` setting or `PYTHONPATH` injection is needed.

`src/intellectaengine/streamlit_app.py` owns UI startup and the small
`intellectaengine` console entry point. Root `app.py` delegates to its `main()`;
`streamlit run app.py` continues to work after installation. The console launcher
replaces its process using `os.execv` and the same Python interpreter's public
`python -m streamlit run` command. Arguments are forwarded unchanged, including
`--` for script arguments; Streamlit owns exit codes and signal/interrupt handling.
No shell or private Streamlit CLI API is used.

After activating the installed environment, launch from any writable directory:

```bash
intellectaengine --server.headless=true --server.port=8501
```

The launcher does not change the working directory. `.env` loads from that
working directory only, with environment variables taking precedence. Relative
`CHROMA_PERSIST_BASE_DIR` values (default `./data/chroma`) remain relative to it;
existing indexes are not moved. Use an absolute persistence path or launch from
the same directory to reuse existing data. Streamlit's own user/current-directory
configuration still applies; the repository's `.streamlit/config.toml` theme is
used when launched there, and is not implicitly loaded outside the checkout.
Configuration, indexes, uploads, logs and model caches are never directed to the
installed package. Choose writable working/persistence directories, not the
installation directory. Merely importing or initially rendering the application
does not create indexes or download models.

The historical `torch.classes.__path__ = []` workaround is removed. The locked
Streamlit 1.64.0 watcher explicitly checks for `_NamespacePath` before reading
`__path__._path`; a fresh-process probe and regression test exercise unmodified
`torch.classes` without warnings. This issue was not specific to Windows or
Python 3.13, despite the old comment. Recheck this test when updating Streamlit.

The canonical reviewed sample is `src/intellectaengine/assets/Chinook.db`.
Its bytes and SHA-256 are unchanged. `importlib.resources.files()` and
`as_file()` resolve it for installed packages, retaining any temporary extraction
until the SQLite connection closes, including failures and interruptions.
`SQLitePolicy.resolve()` is now a context manager; callers must use `with` so
resource paths cannot outlive their extraction. `USE_SAMPLE_DB`, custom-path
approval, native read-only enforcement and all SQL budgets are unchanged.
The precise `.gitignore` exception and publication tests reference this one file.

Setuptools 84.0.0 is the sole build backend, pinned in `[build-system]` to the
version already in the lock. No runtime or development dependency versions were
changed or added. `uv.lock` now records an editable project instead of a virtual
project; dependency exports still omit the project. `MANIFEST.in` explicitly
selects sdist inputs, and wheel package data includes only Chinook. Both artifacts
include `LICENSE` and `THIRD_PARTY_NOTICES.md` (wheel notices live in
`.dist-info/licenses/`). The sdist also includes tests, docs, configuration examples,
lock/exports and the verification scripts; Git metadata is not required to build.

`uv build` produces wheel and sdist in `dist/`. The distribution check command
above checks exact archive path allowlists and the sample checksum, then rebuilds
the sdist and compares all wheel file contents. It creates a temporary environment
without system site packages, installs hashed exported dependencies and the wheel,
and runs `pip check`. The exported dependencies are installed independently of
project uv configuration, with hash verification and pip-compatible index selection.
An empty working directory, isolated Python mode (`-I`),
module-origin assertions, and wheel installation metadata prevent accidental use
of the editable checkout. Offline socket-blocked checks exercise lightweight
imports, headless missing-key dispatch, sample querying, initial Streamlit
rendering, and the installed launcher. No paid calls, pages or model downloads
are used. Temporary verification environments are removed automatically.

Use `uv run --frozen python scripts/check_distribution.py --offline` to require
cached dependency/build artifacts; otherwise uv reuses its cache and fetches
missing installation artifacts. Network access is only for installation/build
metadata, not application checks. To verify a fresh editable setup without
changing `.venv`, Linux users can run:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/intellecta-dev-check uv sync --locked
UV_PROJECT_ENVIRONMENT=/tmp/intellecta-dev-check uv run --frozen python -m pip check
UV_PROJECT_ENVIRONMENT=/tmp/intellecta-dev-check uv run --frozen pytest
```

Keep dependency updates and generated exports on the commands above; no task
runner or new CLI framework is required. Existing pinned CI actions and advisory
exceptions are preserved. Phase 7 stops at packaging; live providers, cross-platform
validation, Docker and deployment remain outside this work.

Phase 7 validation (CPython 3.12.3 / Linux): **395 passed, 1 skipped** in both
existing and freshly created editable environments. The sole skip is unavailable
Git metadata; the existing LangChain Community deprecation warning remains.
Locked sync, `pip check`, both documented Ruff checks, test formatting and generated
export consistency passed. Runtime/development exports are byte-identical to the
Phase 6 exports; only the project's source mode changed in `uv.lock`.

Wheel and sdist allowlists passed (38 wheel files, 71 sdist files), including
unchanged Chinook and both notices, with no private/runtime artifacts. Rebuilding
the sdist reproduced identical wheel file contents. A separate fresh environment
installed the hashed dependencies and wheel, passed `pip check`, proved wheel
module origins outside the checkout, queried the sample read-only, and rendered
the initial UI with missing credentials and Internet sockets blocked. Installed
launcher help and invalid-option exit status checks passed; unit checks cover
unchanged argument forwarding and interrupt propagation. Missing locked dependency
artifacts and registry metadata required installation downloads initially; no model
weights or live application services were used. This is initial rendering through
Streamlit's test harness, not a browser session or live-provider compatibility test.

## Docker workflow (Phase 8)

### Image and supported platform

`Dockerfile` installs the application wheel non-editably into `/opt/venv`. A build
stage installs only the hash-locked `requirements.txt` export with
`--require-hashes --only-binary=:all:` and builds the application with
`--no-deps --no-build-isolation`. Setuptools 84.0.0 comes from that export and
matches the pinned build backend. A BuildKit pip cache preserves completed public
dependency downloads across build retries; it is not an image layer or runtime
model cache. Downloads use a finite 120-second socket timeout and five connection
retries. The final stage copies the installed environment
and the reviewed Streamlit theme; no checkout, test suite, compiler, uv, or extra
development environment is installed. `setuptools` and `build` remain because
PyTorch and Chroma respectively declare them as runtime dependencies. Removing
these would break dependency consistency. No additional OS packages are necessary
for the supported native wheels; `apt-get` is not used.

The supported container target is **Linux amd64**, with CPU-only PyTorch and
CPython 3.12. Docker Desktop must use Linux containers. ARM native builds and
emulation on Apple Silicon are unverified; the multi-architecture base index alone
does not establish support for every locked native wheel. Use `--platform
linux/amd64` as documented. The existing full embedding/provider dependency set
makes this a substantial image (approximately 3.10 GB in the local Docker image
inspection) despite the slim base; removing providers to shrink
it would change behavior and is outside Phase 8. Model weights are not included.

The base is `python:3.12.14-slim-bookworm`, pinned to the registry-verified index
`sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`.
On 2026-09-26, `docker buildx imagetools inspect python:3.12.14-slim-bookworm`
resolved that index and its amd64 manifest
`sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a`.
To update, inspect the intended Python 3.12 slim Bookworm tag, verify the registry
digest and amd64 manifest, update the single `FROM` pin, and rerun the container
and regression checks. Do this deliberately for Python/Debian security updates;
the digest does not update itself. See the [official Python image source](https://github.com/docker-library/python)
and [Docker image digest documentation](https://docs.docker.com/dhi/core-concepts/digests/).

Pinned Python packages alone do not make arbitrary builds reproducible. This pin
also fixes the base's Python, pip and OS files; there are no later OS-package
resolutions. Hashes fix accepted dependency artifacts, while public registries
must still retain/provide them. The wheel-only build fails rather than fetching
unconstrained source-build dependencies. Image metadata/build timestamps need not
be byte-identical. First-use remote model artifacts and provider responses are
separate, unpinned inputs; caching weights is not a model-version guarantee.
If an OS package becomes necessary, document its reason and pin/snapshot strategy
before adding a mutable `apt-get install` step.

### Build inputs and credentials

`.dockerignore` starts with `**` and explicitly re-admits only the reviewed source
modules, packaging metadata, runtime dependency export, sample and theme needed
for the image. Keep its module list current when adding a source module. The
Dockerfile uses selected `COPY` inputs. Private `.env` files, `container.env`, Git,
virtual environments, indexes/other databases, uploads, logs, caches, weights and
credentials never belong in the build context. Only
`src/intellectaengine/assets/Chinook.db` is admitted as database data.

`python3 scripts/check_container.py` copies only these public inputs into a
separate fixture and adds synthetic secrets/runtime artifacts there. Docker's
actual context filtering is tested via a scratch build/export against an exact
file allowlist. It then builds the real image from that fixture and scans the
exported runtime filesystem for synthetic sentinel bytes. It never reads the
developer's private `.env`. Build stages receive no credentials, secret build
arguments, or secret Dockerfile environment values. Dependency downloads are
build activity, distinct from the offline application checks.

### Run and configure

The README contains the direct build/run/stop commands. The exec-form CMD launches
`intellectaengine`, whose existing `os.execv` replaces it with Streamlit as PID 1.
The application runs as UID/GID **10001:10001**, binds `0.0.0.0:8501` inside the
container and retains CORS/XSRF defaults. Usage statistics are disabled. Docker's
`SIGTERM` reaches Streamlit directly; the recommended stop timeout is 20 seconds.
The stdlib `urllib.request` health check probes `/_stcore/health` with a 3-second
HTTP timeout and a 5-second Docker timeout. A healthy server does not establish
provider availability, credentials, model capabilities, or successful LLM requests.

Compose 2.24+ provides one application service, loopback publishing and named
volumes; its optional file uses the
[documented `required: false` setting](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/).
Use `docker compose --env-file /dev/null ...` to avoid implicit loading
of the checkout's `.env` for Compose interpolation. The optional `container.env`
is an explicitly operator-created runtime file; it is not included in the image.
A Docker CLI `--env-file` likewise injects environment settings, not a file.
Never pass keys as build arguments. Container environment is visible to operators
who control Docker; this is a local single-user workflow, not a secret vault.

AppSettings precedence remains process environment, then `/app/.env` (the working
directory), then application defaults. No `.env` is shipped; an intentional
read-only mount to `/app/.env` is possible, but image ENV values such as
`CHROMA_PERSIST_BASE_DIR` take precedence over that file. Runtime `--env-file` or
`-e` can override image defaults (`-e` wins); Compose `environment` overrides its
`env_file`. Restart/recreate after changing settings. Do not blindly reuse host
relative paths from `.env.example`. Neither Docker nor Compose automatically
imports the host's application environment variables in the provided commands.

### Writable paths and persistence

| Path / variable | Default in image | Lifetime with recommended volumes |
| --- | --- | --- |
| `CHROMA_PERSIST_BASE_DIR` | `/data/chroma` | Chroma named volume |
| `HOME` | `/home/app` | Writable container home; recreated with container |
| `XDG_CACHE_HOME` | `/home/app/.cache` | Model cache named volume |
| `HF_HOME` | `/home/app/.cache/huggingface` | Model cache named volume |
| `SENTENCE_TRANSFORMERS_HOME` | `/home/app/.cache/sentence-transformers` | Model cache named volume |
| `FASTEMBED_CACHE_PATH` | `/home/app/.cache/fastembed` | Model cache named volume |
| temporary files | `/tmp` | Container lifetime |

The locked LangChain HuggingFace wrapper passes `cache_folder=None` to Sentence
Transformers, whose base model reads `SENTENCE_TRANSFORMERS_HOME`. Hugging Face Hub
also honors `HF_HOME`. The locked FastEmbed wrapper passes `cache_dir=None`;
FastEmbed's `define_cache_dir` reads **`FASTEMBED_CACHE_PATH`**, otherwise it would
use a temporary directory. These actual integration paths were inspected; the
smoke check validates FastEmbed's resolver without initializing an embedder.
ONNX Runtime imports also create cache metadata; native CPU/cache-resolver checks
run in a separate disposable container so they do not contaminate the pristine
startup/persistence checks.
First embedding use may download weights to these locations; startup and builds
do not. Actual model downloads/retrieval quality are deliberately untested.

Image directories are prepared for UID/GID 10001. Docker populates a fresh named
volume from the mount destination, including its ownership, so the application
can write without a root entrypoint. Keep default volume copy behavior; do not
use `volume-nocopy`. See [Docker volume population](https://docs.docker.com/engine/storage/volumes/).
Existing volumes retain existing ownership and contents. A host bind mount masks
the prepared directory: if using one, first create the directory and explicitly
give UID/GID 10001 access on the Docker host. Repair only the specific directory
or volume you own if migrating older data; do not run the app as root or use
`chmod 777`. Docker/user-namespace mappings may require host-specific ownership.

`docker rm` and `docker compose ... down` preserve named volumes; Compose
`down -v` destroys those volumes. Direct Docker and Compose use different volume
names unless configured otherwise. Home files outside `.cache` and `/tmp` are
not persisted. **Preserving Chroma files does not restore Streamlit sessions,
chat history, upload bytes, or session-owned document handles. It does not add a
saved-document-library feature.** The smoke test writes a synthetic Chroma
collection with explicit vectors (no embedder) and cache marker files, recreates
the container, and reads them back. This tests disk persistence only.

### Optional custom SQLite and existing Ollama

Custom SQLite remains opt-in. Mount an existing operator-reviewed database or
small directory read-only, readable by UID 10001, and approve **container** paths:

```bash
# Add these options before the image name in the README's docker run command:
--mount type=bind,src=/absolute/host/reviewed-db,dst=/approved-db,readonly \
-e 'SQL_ALLOWED_ROOTS=["/approved-db"]'
```

Enter `sqlite:////approved-db/example.db` in the UI. Do not mount unrelated private
data. The bundled `USE_SAMPLE_DB` requires no mount or custom SQL roots and remains
read-only through the existing SQL policy.

For an **already running** Ollama server, set runtime configuration, for example:

```dotenv
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
DEFAULT_OLLAMA_MODEL=your-already-installed-model
```

[Docker Desktop supplies `host.docker.internal`](https://docs.docker.com/desktop/features/networking/networking-how-tos/).
On Linux Docker Engine, add
`--add-host host.docker.internal:host-gateway` to `docker run`, or an `extra_hosts`
entry `host.docker.internal:host-gateway` under Compose's `app` service. Container
`localhost` is the container itself. The host Ollama listener must already accept
connections from the Docker bridge/host gateway, with suitable firewall restrictions;
a host-loopback-only listener is not reachable via that gateway. A reachable LAN
server URL is another option. Do not expose Ollama publicly for this workflow.
No Ollama service, model download, or server reconfiguration is performed here.

### Verification and handoff

```bash
python3 scripts/check_container.py
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen ruff check tests --select E4,E7,E9,F
uv run --frozen ruff format --check tests
uv run --frozen python -m pip check
uv build
uv run --frozen python scripts/check_distribution.py --offline
```

The container smoke check requires only host Python's standard library and Docker
with Buildx. The CI container job runs it separately from the unchanged baseline
job and uses the existing pinned checkout action. It builds a real image, starts
it with `--network=none` and offline model flags, waits for Docker health, checks
non-root identity and wheel installation, runs dependency consistency, renders the
initial UI through Streamlit's test harness with Internet sockets blocked and
model constructors guarded, queries/checksums Chinook, and checks writable paths,
synthetic persistence and graceful exit code 0 after SIGTERM. The image contains
no test dependencies; probe scripts are supplied via `docker exec` stdin. Temporary
containers, named volumes and image tags are cleaned up by the host script.

Docker unavailability is reported with exit code 2 and the exact unverified scope;
it is not a passing container test. The script never installs/starts a daemon or
changes Docker socket permissions. Health and AppTest do not constitute a browser
interaction test, real model quality assessment or provider compatibility test.
Application dependencies, lock/exports, SQL/web/RAG policies and advisory exceptions
remain unchanged. Phase 8 stops here; demo polish and the final README redesign
remain later work.

### Phase 8 validation results

Verified locally on Linux amd64 with CPython 3.12.3 for the host checks and
CPython 3.12.14 in the image. The final offline regression run: **395 passed,
1 skipped** (unavailable Git metadata); the existing LangChain Community
deprecation warning remains. Both documented Ruff checks, test formatting,
additional correctness lint/formatting for the container scripts, dependency
consistency, and generated dependency-export comparisons passed.

The real Docker image built successfully. The complete `check_container.py` run
passed exact context/synthetic-secret exclusions, runtime filesystem sentinel
scanning, native CPU imports/cache resolvers, non-root wheel installation,
Streamlit health, initial offline UI rendering, unchanged read-only Chinook,
security/theme/statistics settings, writable paths, synthetic Chroma/cache
persistence across recreation, and two SIGTERM stops with exit code 0 before
20 seconds. The initial-render check also verifies no Chroma/model cache files
are created by startup. No embedding model was initialized or downloaded.

Separate checks passed real HTTP health through `127.0.0.1:8501`, the documented
Compose service lifecycle and volume retention after `down`, synthetic runtime
`--env-file` versus working-directory `.env` precedence, and a synthetic read-only
SQLite mount approved by its container path. Verification never read the
operator's private `.env`. Test containers and synthetic volumes were removed;
`intellectaengine:local` and the build dependency cache remain available.

Earlier validation failures were corrected and rerun: directory allow rules were
made restrictive after a synthetic-context failure; registry read timeouts led
to the bounded build timeout/cache; the UI probe now parses the real CLI options
before checking Streamlit environment settings; native ONNX cache side effects
are isolated from startup/persistence probes; and the optional SQLite probe uses
the existing quoted-string result format. Startup/exclusion/persistence assertions
were retained. Bare-mode Streamlit harness warnings are expected.

GitHub-hosted execution, Docker Desktop/ARM/emulation, live providers, first-use
model downloads and real-model quality were not exercised. No deployment,
public multi-user support, Git initialization, commit or push is part of Phase 8.
The handoff is the local image, README commands and repeatable CI smoke script;
stop here before demo polish and the final README redesign.

## Documentation, examples, and browser evidence (Phase 9)

The README now introduces the problem, actual interface, code-backed engineering
choices, small Mermaid architecture, one pinned-uv/Python 3.12 quickstart,
Docker/Compose persistence semantics, example questions, checks, and limitations.
[architecture.md](architecture.md) maps the actual classes and explains caller-owned
turn commits, forced web without an LLM, SQLite-only enforcement, replace-on-success
ingestion, provider disclosures, and Jina's separate origin fetch. Earlier phase
handoffs above remain historical records; Phase 9 supersedes their pending-demo notes.

[examples/](../examples/README.md) contains a two-page original fictional PDF,
plain editable source, and three aggregate Chinook queries with exact expected
policy output. The generator uses authoring-only ReportLab 4.4.9 with deterministic
metadata and standard PDF fonts; application dependencies/lock/exports are unchanged.
Both pages were rendered with Poppler and visually reviewed. Regeneration produced
identical bytes (SHA-256 `05e1955d134b2aa69b5c9ef36ce52420ad2168df203959fb788289df160dcce3`).
An initial text check caught hyphenated words wrapping between lines; disabling
hyphen-based wrapping made complete source paragraphs extract faithfully.

Two meaningful regressions verify source text/page metadata through the actual
`DocumentIngestionService` and temporary Chroma with deterministic fake embeddings,
and all analytical reference statements through the existing read-only SQLite
policy. They do not assert README wording or evaluate live inference. The reviewed
Chinook database is unchanged.

[demo.md](demo.md) records actual Chromium/Playwright viewport screenshots of the
normal application, isolated from the checkout's private `.env`, browser accounts,
and existing session state. Empty credentials, offline model flags, a temporary
home/cwd, disabled usage statistics, and blocked external browser requests were
used. The optional external font stylesheet was blocked; fallback fonts rendered.
The normal app performed sample connection and schema discovery. No fake providers,
fake web responses, scripted answers, or demo mode were needed. The reproduction
script only drives browser controls and captures pixels; no production code changed.
Initial placeholder widgets were resolved by waiting for readiness, and the custom
checkbox was operated through its visible label. No presentation fix was required.

The packaging decision is explicit: the sdist includes documentation, the two
reviewed PNGs, original PDF/source, SQL references, generator, capture script, and
example tests so docs links and tests work from a source release. `MANIFEST.in`
and the exact distribution allowlist name binary/example/capture assets explicitly.
The runtime wheel continues to contain only application modules, Chinook, and
standard metadata/license files (its metadata includes the README text). The
existing Docker deny-by-default context excludes docs/examples/scripts. Container
exclusion probes now include synthetic Phase 9 asset paths. No runtime dependency,
Docker build input exception, provider interface, or application behavior changed.

Phase 9 validation: **397 passed, 1 skipped** (unavailable Git metadata),
with the existing LangChain Community deprecation warning. Locked offline sync,
Ruff correctness checks, test/new-script formatting, dependency consistency,
PDF byte reproducibility, locked runtime/development export comparisons, and
exact local Markdown link/anchor checks passed.
Node syntax checking and real browser startup/connect/schema/disconnect/reconnect/
reset checks passed with Playwright 1.62.1 / Chromium 151.0.7922.34. Both PNGs were
visually inspected for readability and accidental disclosure. No model cache was
created by the browser walkthrough. Docker's actual scratch-build context export
matched the exact allowlist and excluded the new synthetic assets/secrets; the
Phase 8 full image/start/stop/persistence smoke suite was not repeated.

The final wheel/sdist check passed exact allowlists (38 wheel files, 87 sdist
files), unchanged Chinook checksum, identical wheel contents rebuilt from the
sdist, and an isolated offline wheel installation. Installed-wheel imports,
headless dispatch, sample querying, AppTest startup, dependency consistency, and
launcher behavior passed. Curated binaries and reproduction assets are included
only in the sdist; no screenshot/example payload is in the runtime wheel.

Mermaid blocks were structurally checked and manually compared with code. No local
Mermaid renderer was available, so diagram rendering remains unverified. Browser
checks, AppTest, scripted executor tests, reference data checks, and live-provider
quality are distinguished in the demo guide. No paid calls, application searches,
model downloads, Git initialization, commits, push, image publication, or deployment
were performed. Stop after Phase 9; full Git history/secret review, hosted CI, and
any desired live-provider demonstration remain for final publication review.

## Known limitations

These are existing issues, not guarantees provided by the baseline tests:

- Embedded Chroma remains local single-user storage. Interrupted replacement cleanup
  may leave an inactive collection; deletion is not secure erasure.
- SQL is limited to approved local SQLite files. Native progress limits do not
  sandbox malicious database files, bound every SQLite allocation, or interrupt
  every blocking OS/provider operation. Remote dialects require their own controls
  and boundary tests before they can be restored.
- Web URL checks cannot control Jina's origin resolution/redirects. DDGS owns its
  internal buffering/pagination; synchronous deadlines are not hard cancellation.
- The UI is synchronous; streaming and asynchronous execution are not implemented.
- The current smoke tests do not exercise paid providers, actual model routing,
  retrieval quality, or live web services.
- Browser checks cover startup and sample connection, not live-model answers or
  PDF upload in a browser. Hosted CI and live-provider quality remain unverified.
  The completed [publication review](release-readiness.md) records conditional
  readiness and remaining publication gates; no public multi-user deployment is claimed.

# Dependency advisory review

Reviewed on 2026-09-24 against the locked Python 3.12 Linux environment.
An advisory audit is evidence about known reports, not a guarantee that a package
or application is secure. This baseline still has application-level issues listed
in [development notes](development.md#known-limitations).

## Remediated dependency findings

The previous Sentence Transformers 3.x constraint forced Transformers 4.x.
The advisory audit reported vulnerabilities in that resolved version. Sentence
Transformers now uses a compatible 5.x release, and the resolver constrains
Transformers to `>=5.10,<6`. Offline import checks cover the resulting stack;
real-model retrieval quality is not established by those tests.

The unused direct `langchain==1.3.4` dependency was removed. The application uses
`langchain-classic`, which is now declared and locked explicitly.

## Chroma server advisories: not applicable to the current execution path

The latest available Chroma 1.x release at review time, 1.5.9, has the following
published advisories with no fixed version reported by the advisory service:

| Advisory | Affected behavior | Current application boundary |
| --- | --- | --- |
| [CVE-2026-45829](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c) | Code injection through the HTTP collection-creation endpoint using remote model code | No Chroma HTTP server is started or exposed; embedding objects are supplied locally by the application. |
| [CVE-2026-45833](https://github.com/advisories/GHSA-36p7-vc44-83pf) | Code injection through the HTTP collection-update endpoint | The application uses embedded persistent Chroma, without that endpoint. |
| [CVE-2026-45830](https://github.com/advisories/GHSA-2wm9-hf6c-p5cr) | Cross-tenant authorization bypass | No Chroma server authentication or tenant authorization is used or claimed. |
| [CVE-2026-45831](https://github.com/advisories/GHSA-xph7-9rjv-w5fr) | Resource-scope bypass in SimpleRBACAuthorizationProvider | The application does not configure this authorization provider. |

These four advisory aliases are explicitly excluded from the **gating** audit in
CI. This is a scoped applicability decision, not a claim that Chroma is patched.
An unfiltered audit still reports them. Inspect `connectors/vectorstore_connector.py`
and `core/embedding_factory.py` when reviewing this decision.

Reassess these exclusions when changing Chroma's version, enabling an HTTP server,
accepting user-defined embedding code, introducing tenants, or adding remote
deployment. Do not reuse this exception list for a hosted Chroma service.

Run the same reviewed audit locally:

```bash
uv run --frozen pip-audit --local \
  --ignore-vuln CVE-2026-45829 \
  --ignore-vuln CVE-2026-45833 \
  --ignore-vuln CVE-2026-45830 \
  --ignore-vuln CVE-2026-45831
```

Run `uv run --frozen pip-audit --local` without exclusions to review all findings.
New applicable findings must be fixed or assessed explicitly rather than silently
added to this list.

## PyTorch CPU wheels

The PyTorch CPU index uses local version suffixes such as `+cpu`. PyPI-based
auditing skips that exact distribution name. CI separately audits the corresponding
public base version (the part before `+`) with dependency resolution disabled.
This covers advisories attached to the base PyTorch release; it does **not**
independently audit CPU wheel contents. `uv.lock` and requirements hashes identify
the installed distributions.

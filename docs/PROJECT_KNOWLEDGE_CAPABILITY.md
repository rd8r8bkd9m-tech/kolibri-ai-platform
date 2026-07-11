# Owner project knowledge capability

`tool:project_knowledge` is a bounded, read-only capability for authenticated
owner requests to `POST /v1/responses`. It is not a public-session tool, a
generic filesystem browser, an internet-search substitute or a wildcard proxy.

The gateway searches only allowlisted documentation/source roots below the
running Kolibri release. It does not follow symlinks and excludes environment,
credential, runtime, artifact, evidence, snapshot and generated dependency
paths. File count, total bytes, per-file bytes, excerpt bytes and result count
are bounded. Returned evidence contains a repository-relative path, exact line
span, file SHA-256 and span SHA-256. Secret-shaped values, internal addresses,
internal URLs and absolute runtime paths are redacted before provider context
or response citations are built.

The owner gateway auto-plans this capability only for explicit project,
repository, project-document, named-person and project-role context. Web
freshness questions do not activate it. Public sessions may still request the
separate controlled `tool:web_search`, but a public request for project
knowledge is rejected with HTTP 422.

The provider must cite the supplied `[P1]`…`[P8]` markers. The deterministic
response verifier rejects an otherwise valid provider answer when project
citations are absent or when it cites a marker not present in the bound tool
result.

## Owner credential file

The unified backend accepts `KOLIBRI_OWNER_API_TOKEN_FILE`, matching the token
file already used by the canonical Telegram gateway. The configured path must
be absolute, regular, non-symlink, bounded, non-world-readable and not writable
by group/other. Only a SHA-256 digest is retained in process authentication
state. An explicitly configured unsafe or unreadable file fails closed with a
bounded configuration error; token bytes and paths are never logged or returned.

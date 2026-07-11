# Vista OS 11.1 Product Release — build report

## Product delta

- one real single-window workspace instead of overlapping demo cards;
- working client projects list and creation of multiple estimates;
- no visible placeholder attachment or voice controls;
- working profile/settings control;
- status lifecycle: draft, review, approved, sent, archived;
- configurable overhead, margin, discount and VAT with server-side recalculation;
- real PDF, XLSX, DOCX, JSON and Markdown generation;
- signed sessions, tenant isolation, expiring/revocable public links;
- persistent queue, leases, worker artifacts, SHA-256 and verifier gate;
- pinned dependency baseline;
- Rust Vista state and capability crates wired into the Tauri shell;
- hardened one-command development and production deployment scripts.

## Local evidence

```text
Python/backend/API tests: 15 passed
Frontend/component/policy tests: 21 passed
Production Vite build: passed
Source secret/security scan: passed, 0 findings
NPM production dependency audit: 0 vulnerabilities
HTTP product smoke: passed
Authenticated factory canary: passed
Backup/restore verification: passed
Production environment readiness: green
One-command development start: passed
```

Evidence is stored in `release-evidence/` in the distributable package and under `var/release-check/` in the working tree.

## Mandatory CI gates not executed in the current sandbox

- browser Playwright E2E for this exact revision;
- `cargo test --workspace` and Tauri `cargo check`;
- Docker image build and container smoke;
- live Control Plane + two independent physical worker nodes.

They are mandatory jobs in `.github/workflows/vista-ci.yml`. A 24/7 distributed-factory claim is prohibited until the physical three-node canary passes.

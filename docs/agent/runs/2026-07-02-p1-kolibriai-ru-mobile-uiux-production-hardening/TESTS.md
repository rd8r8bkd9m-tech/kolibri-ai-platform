# Tests

## Commands Run

```text
git diff --check
```

Result: passed.

```text
npm run build
```

Working directory: `remote/kolibriai-frontend`

Result: passed.

Notes:
- The environment uses Node.js `18.19.1`.
- Vite emitted a version warning because it requests Node.js `20.19+` or `22.12+`.
- Despite the warning, TypeScript and Vite completed successfully and produced `dist/`.

```text
file remote/kolibriai-frontend/evidence/mobile-2026-07-02/*.png
```

Result: passed. All screenshot evidence files are valid PNG images.

## Focus

- Mobile safe-area behavior.
- Estimate list and estimate editor mobile layout.
- Keyboard resize screenshot evidence.
- Offline API state screenshot evidence.
- Production build health for the recovered frontend.

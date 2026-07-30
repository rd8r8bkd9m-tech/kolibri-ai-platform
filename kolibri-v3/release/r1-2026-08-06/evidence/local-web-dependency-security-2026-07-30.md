# Local web dependency security gate

Captured: 2026-07-30  
Scope: canonical V3 Next.js web package

## Result

`PASSED` for the web package.

The inherited Next.js dependency graph initially reported three high-severity
findings through its pinned PostCSS 8.4.31 and Sharp 0.34.5 dependencies. A
scoped `next` override now resolves:

- PostCSS 8.5.25;
- Sharp 0.35.3 and its matching libvips platform packages.

No forced npm remediation or framework downgrade was used.

## Verification

```text
Web audit before:  3 high
Web audit after:   0 vulnerabilities
npm ci --dry-run:  passed
Web tests:         99/99 passed
TypeScript:        passed
Next production build: passed
Sharp smoke:       sharp 0.35.3 / libvips 8.18.3
git diff --check:  passed
```

## Separate Expo risk

The Expo SDK 57 package was not changed by this gate. Its audit still reports
development/build-tool findings:

- 9 high findings in the dev/lint minimatch chain;
- 11 moderate findings in Expo/Xcode build tooling with dev dependencies
  omitted.

`npm audit fix` proposes an incompatible Expo SDK 57 to 46 downgrade, so it
was rejected. Mobile tests remain 5/5 and mobile typecheck passes. This stays
an explicit Expo dependency gate rather than being hidden inside the green
web result.

Production was not contacted or changed.

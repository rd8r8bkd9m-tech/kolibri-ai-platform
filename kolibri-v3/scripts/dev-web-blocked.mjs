#!/usr/bin/env node

console.error(
  [
    "Kolibri V3 frontend-only development is disabled.",
    "Run `npm run dev` from kolibri-v3 so migrations, owner preflight,",
    "launch-bound backend health, and frontend lifecycle stay supervised.",
  ].join(" "),
);
process.exitCode = 2;


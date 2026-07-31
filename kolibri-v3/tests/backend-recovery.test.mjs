import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const identityProvider = readFileSync(
  new URL("../lib/identity/provider.tsx", import.meta.url),
  "utf8",
);

test("identity automatically recovers after a transient backend restart", () => {
  assert.match(identityProvider, /OFFLINE_RETRY_MS\s*=\s*1_500/);
  assert.match(identityProvider, /if \(status !== "offline"\) return/);
  assert.match(
    identityProvider,
    /setTimeout\(async \(\) => \{[\s\S]*await refresh\(\)[\s\S]*retry\(\)/,
  );
  assert.match(identityProvider, /clearTimeout\(retryTimer\)/);
});

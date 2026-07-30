import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("the mobile browser client is the Expo Assistant UI workspace", async () => {
  const [rootPackage, mobilePackage, expoConfig, runtime, webSession] =
    await Promise.all([
      read("package.json").then(JSON.parse),
      read("apps/kolibri-mobile/package.json").then(JSON.parse),
      read("apps/kolibri-mobile/app.json").then(JSON.parse),
      read("apps/kolibri-mobile/src/product-chat/runtime-provider.tsx"),
      read("apps/kolibri-mobile/src/auth/mobile-session.web.tsx"),
    ]);

  assert.deepEqual(rootPackage.workspaces, ["apps/kolibri-mobile"]);
  assert.equal(
    mobilePackage.dependencies["@assistant-ui/react-native"],
    "0.1.33",
  );
  assert.equal(mobilePackage.dependencies["react-native-web"], "~0.21.2");
  assert.equal(expoConfig.expo.web.output, "single");
  assert.equal(expoConfig.expo.experiments.baseUrl, "/app");
  assert.match(runtime, /AssistantRuntimeProvider/);
  assert.match(runtime, /useAgUiRuntime/);
  assert.match(webSession, /credentials: "same-origin"/);
  assert.match(webSession, /"\/api\/v3\/session"/);
  assert.doesNotMatch(webSession, /expo-secure-store|refreshToken/);
});

test("one release build emits mobile SPA before the desktop application", async () => {
  const [rootPackage, proxy, installer] = await Promise.all([
    read("package.json").then(JSON.parse),
    read("proxy.ts"),
    read("deploy/portable/install.sh"),
  ]);

  assert.equal(
    rootPackage.scripts.build,
    "npm run build:mobile && npm run build:web",
  );
  assert.match(rootPackage.scripts["build:mobile"], /kolibri-mobile/);
  assert.match(proxy, /MOBILE_USER_AGENT/);
  assert.match(proxy, /assets\\\//);
  assert.match(proxy, /destination\.pathname = "\/app\/index\.html"/);
  assert.match(installer, /cp -a "\$build_root\/public"/);
  assert.doesNotMatch(installer, /cp -a "\$source_root\/public"/);
});

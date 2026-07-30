// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist*/**", "../../public/app/**"],
    rules: {
      "import/no-unresolved": [
        "error",
        { ignore: ["^@/src/auth/mobile-session$"] },
      ],
    },
  },
]);

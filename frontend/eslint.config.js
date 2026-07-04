import js from "@eslint/js";

export default [
  {
    ignores: [
      "dist/**",
      "node_modules/**"
    ]
  },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        window: "readonly",
        document: "readonly",
        localStorage: "readonly",
        console: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        process: "readonly",
        URLSearchParams: "readonly",
        HTMLDivElement: "readonly",
        FileReader: "readonly",
        URL: "readonly"
      }
    }
  }
];

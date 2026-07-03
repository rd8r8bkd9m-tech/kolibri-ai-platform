import js from "@eslint/js"
import globals from "globals"

export default [
  {
    ignores: ["dist/**", "node_modules/**", "src/**/*.tsx"],
  },
  {
    files: ["src/**/*.{js,jsx}", "tests/**/*.mjs", "vite.config.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      ...js.configs.recommended.rules,
    },
  },
]

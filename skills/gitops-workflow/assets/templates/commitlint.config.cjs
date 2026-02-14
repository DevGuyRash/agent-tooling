// commitlint.config.cjs
// Copy this file to your repo root as `commitlint.config.cjs` (or .js) to enable commitlint.
//
// Requires:
//   npm i -D @commitlint/cli @commitlint/config-conventional
//
// See: https://commitlint.js.org/

module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "refactor",
        "test",
        "chore",
        "perf",
        "ci",
        "build",
        "style",
        "deps",
        "security",
        "revert",
        "hotfix",
      ],
    ],
    // Enforce lowercase subject (best-effort; not perfect for acronyms)
    "subject-case": [2, "always", ["lower-case"]],
    // Conventional Commits recommends <= 100; many teams prefer ~72
    "header-max-length": [2, "always", 100],
  },
};

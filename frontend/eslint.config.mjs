import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import boundaries from "eslint-plugin-boundaries";

// Feature-Sliced Design import rule: app -> widgets -> features -> entities -> shared (ARCHITECTURE.md §14).
const layers = ["app", "widgets", "features", "entities", "shared"];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "import/resolver": { typescript: { alwaysTryTypes: true } },
      "boundaries/elements": layers.map((type) => ({ type, pattern: `src/${type}` })),
    },
    rules: {
      "boundaries/dependencies": [
        2,
        {
          default: "disallow",
          policies: layers.map((type, i) => ({
            from: { element: { type } },
            allow: { to: { element: { types: layers.slice(i) } } },
          })),
        },
      ],
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/shared/api/schema.d.ts"]),
]);

export default eslintConfig;

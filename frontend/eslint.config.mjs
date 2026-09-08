// Flat config. ESLint 9 dropped .eslintrc and Next 16 removed `next lint`, so
// `pnpm lint` runs the eslint binary against this file directly.
//
// eslint-config-next 16 ships native flat configs, so they are imported as-is.
// Do not reach for FlatCompat here: wrapping the already-flat config trips a
// circular-structure error in the eslintrc validator.
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
];

export default config;

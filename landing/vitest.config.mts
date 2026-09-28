import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    // Mirrors the `@/*` path in tsconfig.json. Vitest does not read tsconfig
    // paths on its own, so the two have to be kept in step.
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    // node, not jsdom: what is under test here is the data layer that decides
    // which numbers the page states as fact, plus the drift guard that reads
    // the dashboard's token file off disk. Neither needs a DOM.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});

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
    // node, not jsdom: what is under test here is the data layer and the mock
    // route handler, both of which are plain Request/Response code. Component
    // rendering is verified against the real server in the ticket notes.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});

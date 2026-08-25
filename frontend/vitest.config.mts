import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 *  Two environments, on purpose.
 *
 *  The library tests (`lib/*.test.ts`) run in node. They are about IndexedDB,
 *  retry budgets and arithmetic, and giving them a DOM would only slow them
 *  down and let a component creep into a file that is supposed to be testing a
 *  function.
 *
 *  Component tests need a DOM and ask for it themselves, with
 *  `// @vitest-environment jsdom` at the top of the file. Vitest 4 dropped
 *  `environmentMatchGlobs`, and the per-file docblock is the better shape
 *  anyway: a test that needs a browser says so where somebody reading it will
 *  see it, rather than in a config file two directories away.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    // jsdom files need a real origin: on the default opaque origin
    // `window.localStorage` is undefined and every resume test threw
    // "Cannot read properties of undefined (reading 'clear')".
    environmentOptions: { jsdom: { url: "http://localhost/" } },
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
  resolve: {
    // fileURLToPath, not URL.pathname: on Windows the pathname form is
    // "/C:/Users/...", which resolves to nothing and every "@" import
    // silently failed to type-resolve there.
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
});

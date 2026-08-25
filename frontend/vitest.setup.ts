/**
 *  Matchers for component tests, and nothing else.
 *
 *  Imported by every test file including the node-environment ones, so this
 *  has to be harmless without a DOM. `jest-dom` only registers matchers, which
 *  is safe; anything that touched `document` would break the library suite.
 */
import "@testing-library/jest-dom/vitest";
import { createRequire } from "node:module";

/**
 *  Node 22+ declares a `localStorage` accessor of its own on globalThis
 *  (undefined unless `--localstorage-file` is given). In Vitest's jsdom
 *  environment `window` *is* globalThis, so that accessor shadows jsdom's
 *  storage and `localStorage.clear()` threw "Cannot read properties of
 *  undefined" in every test that touched it -- the resume-after-reload
 *  contract was not being tested at all. Plain jsdom on this Node does
 *  provide storage, so borrow a real jsdom Storage for the same origin.
 *  Node-environment files have no `document` and are left alone.
 */
if (typeof document !== "undefined"
    && typeof (globalThis as { localStorage?: unknown }).localStorage === "undefined") {
  // `createRequire` rather than a top-level await: `next build` type-checks
  // this file and a top-level await is not allowed under its module target.
  const { JSDOM } = createRequire(import.meta.url)("jsdom");
  const origin = new JSDOM("", { url: document.location?.href || "http://localhost/" }).window;
  Object.defineProperty(globalThis, "localStorage",
    { value: origin.localStorage, configurable: true, writable: true });
  Object.defineProperty(globalThis, "sessionStorage",
    { value: origin.sessionStorage, configurable: true, writable: true });
}

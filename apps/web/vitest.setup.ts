import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Unmount React trees between tests so component state never leaks across them.
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

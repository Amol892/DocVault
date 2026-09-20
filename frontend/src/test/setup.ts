// Types for the jest-dom matchers (toBeInTheDocument, ...).
import "@testing-library/jest-dom/vitest";
import * as matchers from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";
import { afterEach, expect } from "vitest";

// Register the matchers on THIS test runner's `expect`. Relying on the package's own
// "/vitest" entry can attach them to a second copy of vitest under pnpm's strict layout.
expect.extend(matchers);

afterEach(() => {
  cleanup();
  localStorage.clear();
});

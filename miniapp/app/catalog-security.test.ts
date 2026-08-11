import { readFileSync } from "node:fs";
import { access } from "node:fs/promises";

import { describe, expect, it } from "vitest";

describe("public catalog boundary", () => {
  it("public question types contain no correct field", () => {
    const source = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/\bcorrect\s*:/);
  });

  it("has no client-owned catalog or link modules", async () => {
    await expect(access(new URL("./diagnostics-catalog.ts", import.meta.url))).rejects.toThrow();
    await expect(access(new URL("./links.ts", import.meta.url))).rejects.toThrow();
  });
});

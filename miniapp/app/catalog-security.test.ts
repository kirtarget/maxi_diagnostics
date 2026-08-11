import { readFileSync } from "node:fs";
import { access } from "node:fs/promises";

import { describe, expect, it } from "vitest";

describe("public catalog boundary", () => {
  it("public question types contain no correct field", () => {
    const source = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/\bcorrect\s*:/);
  });

  it("keeps expected answers in the post-completion contract only", () => {
    const types = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
    const publicQuestionBlock = types.slice(
      types.indexOf("type BaseQuestion"),
      types.indexOf("export type AnswerValue"),
    );
    expect(publicQuestionBlock).not.toContain("correct");
    expect(publicQuestionBlock).not.toContain("expected_answer");
    expect(types).toContain("export type ReviewItem");
    expect(types).toContain("expected_answer: string");
    expect(types.indexOf("expected_answer")).toBeGreaterThan(
      types.indexOf("export type ReviewItem"),
    );
  });

  it("has no client-owned catalog or link modules", async () => {
    await expect(access(new URL("./diagnostics-catalog.ts", import.meta.url))).rejects.toThrow();
    await expect(access(new URL("./links.ts", import.meta.url))).rejects.toThrow();
  });
});

import { describe, expect, it } from "vitest";

import { hasApprovedPrimaryScore } from "./question-metadata";

describe("primary score attribution", () => {
  it("shows primary points only after source approval", () => {
    expect(hasApprovedPrimaryScore(undefined)).toBe(false);
    expect(hasApprovedPrimaryScore({
      provider: "maximum",
      official_year: 2026,
      approval_status: "draft",
      source_kind: "original",
      source_url: "https://maximumtest.ru/",
      rights_status: "original",
      verified_at: "2026-09-01",
    })).toBe(false);
    expect(hasApprovedPrimaryScore({
      provider: "maximum",
      official_year: 2026,
      approval_status: "approved",
      source_kind: "original",
      source_url: "https://maximumtest.ru/",
      rights_status: "original",
      verified_at: "2026-09-01",
    })).toBe(true);
  });
});

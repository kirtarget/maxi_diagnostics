import { describe, expect, it } from "vitest";

import { formatLeagueDates, parseLeagueResponse } from "./league-model";

describe("parseLeagueResponse", () => {
  it("localizes API week dates as a compact Russian range", () => {
    expect(formatLeagueDates("2026-09-07", "2026-09-13")).toBe("7–13 сентября");
  });
  it("keeps API calendar dates stable even when timestamps carry a negative offset", () => {
    expect(formatLeagueDates("2026-09-07T00:00:00-07:00", "2026-09-13T00:00:00-07:00")).toBe("7–13 сентября");
  });
  it("falls back to the raw range for invalid or already localized dates", () => {
    expect(formatLeagueDates("2026-02-31", "2026-03-07")).toBe("2026-02-31 · 2026-03-07");
    expect(formatLeagueDates("7 августа", "13 августа")).toBe("7 августа · 13 августа");
  });
  it("preserves the server row order and values", () => {
    const parsed = parseLeagueResponse({
      status: "active",
      week_start: "2026-08-24",
      week_end: "2026-08-30",
      rows: [
        { rank: 4, display_label: "Синий маяк", xp_week: 40, is_me: false },
        { rank: 1, display_label: "Тихий космос", xp_week: 90, is_me: true },
      ],
      me: { rank: 1, xp_week: 90 },
    });
    expect(parsed?.rows.map((row) => row.display_label)).toEqual(["Синий маяк", "Тихий космос"]);
    expect(parsed?.rows.map((row) => row.rank)).toEqual([4, 1]);
  });

  it("does not calculate a rank or XP when the server omits them", () => {
    expect(parseLeagueResponse({
      status: "active",
      week_start: "2026-08-24",
      week_end: "2026-08-30",
      rows: [{ display_label: "Синий маяк", is_me: false }],
      me: null,
    })).toBeNull();
  });

  it("rejects legacy row fields outside the privacy allowlist", () => {
    expect(parseLeagueResponse({
      status: "active",
      week_start: "2026-08-24",
      week_end: "2026-08-30",
      rows: [{ rank: 1, display_name: "legacy", xp_week: 10, me: true }],
      me: null,
    })).toBeNull();
  });

  it("accepts a forming league without inventing rows", () => {
    expect(parseLeagueResponse({ status: "forming", week_start: "2026-08-24", week_end: "2026-08-30", rows: [], me: null })).toMatchObject({ status: "forming", rows: [] });
  });
});

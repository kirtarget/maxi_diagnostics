export type LeagueStatus = "forming" | "active";

export type LeagueRow = {
  rank: number;
  display_label: string;
  xp_week: number;
  is_me: boolean;
};

export type LeagueMe = {
  rank: number | null;
  xp_week: number;
};

export type LeagueResponse = {
  status: LeagueStatus;
  week_start: string;
  week_end: string;
  rows: LeagueRow[];
  me: LeagueMe | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function finiteInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : null;
}

function nonnegativeInteger(value: unknown): number | null {
  const normalized = finiteInteger(value);
  return normalized !== null && normalized >= 0 ? normalized : null;
}

function parseRow(value: unknown): LeagueRow | null {
  if (!isRecord(value) || typeof value.display_label !== "string" || typeof value.is_me !== "boolean") return null;
  const rank = nonnegativeInteger(value.rank);
  const xpWeek = nonnegativeInteger(value.xp_week);
  if (rank === null || xpWeek === null) return null;
  return {
    rank,
    display_label: value.display_label,
    xp_week: xpWeek,
    is_me: value.is_me,
  };
}

function parseMe(value: unknown): LeagueMe | null | undefined {
  if (value === null) return null;
  if (!isRecord(value)) return undefined;
  const rank = value.rank === null ? null : nonnegativeInteger(value.rank);
  const xpWeek = nonnegativeInteger(value.xp_week);
  if (rank === undefined || xpWeek === null) return undefined;
  return { rank, xp_week: xpWeek };
}

/**
 * Accept only the public league projection. The server owns row order, rank,
 * XP, and the identity marker, so this function deliberately does not sort or
 * infer any of those values.
 */
export function parseLeagueResponse(value: unknown): LeagueResponse | null {
  if (!isRecord(value) || (value.status !== "forming" && value.status !== "active")) return null;
  if (typeof value.week_start !== "string" || typeof value.week_end !== "string" || !Array.isArray(value.rows)) return null;
  const rows: LeagueRow[] = [];
  for (const row of value.rows) {
    const parsed = parseRow(row);
    if (!parsed) return null;
    rows.push(parsed);
  }
  const me = parseMe(value.me);
  if (me === undefined) return null;
  return {
    status: value.status,
    week_start: value.week_start,
    week_end: value.week_end,
    rows,
    me,
  };
}

export type LeagueScreenState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: LeagueResponse };

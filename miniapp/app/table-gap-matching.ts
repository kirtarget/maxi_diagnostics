import type { InputQuestion } from "./types";

export type TableGapCell = { text: string; marker?: string };

export type TableGapPrompt = {
  headers: string[];
  rows: TableGapCell[][];
  markers: string[];
  options: Array<{ marker: string; label: string }>;
  allowReuse: boolean;
};

const GAP = /^\s*(?:_+\s*)?\(([А-ЯЁ])\)\s*(?:_+)?\s*$/u;
const OPTION = /^(\d)[.)]\s*(.+?)\s*[;.]?$/u;
const TABLE_OPTION = /(?:^|\s)(\d)[.)]\s*(.*?)(?=\s+\d[.)]\s+|$)/gu;
const LIST_HEADING = /^(?:пропущенные элементы|список\b|варианты ответов|элементы для выбора)\s*:/iu;

function pipeCells(line: string): string[] | null {
  if (!/\s\|\s/u.test(line)) return null;
  const cells = line.split("|").map((cell) => cell.trim());
  return cells.length >= 2 ? cells : null;
}

function isGapCell(value: string): boolean {
  return GAP.test(value);
}

function gapMarker(value: string): string | null {
  const match = GAP.exec(value);
  return match?.[1] ?? null;
}

function parseOptions(lines: string[]): Array<{ marker: string; label: string }> {
  const options: Array<{ marker: string; label: string }> = [];
  for (const line of lines) {
    const cells = pipeCells(line) ?? [line];
    for (const cell of cells) {
      const direct = OPTION.exec(cell);
      if (direct) {
        options.push({ marker: direct[1], label: direct[2].trim() });
        continue;
      }
      for (const match of cell.matchAll(TABLE_OPTION)) {
        const label = match[2].trim();
        if (label) options.push({ marker: match[1], label });
      }
    }
  }
  return options.sort((left, right) => Number(left.marker) - Number(right.marker));
}

function isOptionMatrixRow(row: string[]): boolean {
  return row.length >= 2 && row.every((cell) => /^\d[.)]?\s*(?:\S.*)?$/u.test(cell.trim()));
}

export function parseTableGapPrompt(
  prompt: string,
  metadata?: Pick<InputQuestion, "answer_format" | "allow_reuse">,
): TableGapPrompt | null {
  if (metadata?.answer_format === "number") return null;

  const lines = prompt.split(/\n+/u).map((line) => line.trim()).filter(Boolean);
  const markerRow = lines.findIndex((line) => {
    const cells = pipeCells(line);
    return cells ? cells.some(isGapCell) : isGapCell(line);
  });
  if (markerRow < 1) return null;

  const pipeCandidates = lines
    .map((line, index) => ({ line, index, cells: pipeCells(line) }))
    .filter((candidate) => candidate.index > 0 && candidate.index < markerRow && candidate.cells && !isOptionMatrixRow(candidate.cells));
  const firstPipeHeader = [...pipeCandidates].reverse().find((candidate) => {
    const next = pipeCells(lines[candidate.index + 1] ?? "");
    return next && next.length === candidate.cells!.length;
  })?.index ?? -1;
  let headers: string[];
  let rawCells: string[];
  if (firstPipeHeader >= 0) {
    headers = pipeCells(lines[firstPipeHeader]) ?? [];
    const rows: string[][] = [];
    for (let index = firstPipeHeader + 1; index < lines.length; index += 1) {
      const row = pipeCells(lines[index]);
      if (!row) break;
      rows.push(row);
    }
    if (!headers.length || rows.length === 0 || rows.some((row) => row.length !== headers.length)) return null;
    rawCells = rows.flat();
  } else {
    const firstOption = lines.findIndex((line, index) => index > markerRow && OPTION.test(line));
    if (firstOption < 0) return null;
    const listHeading = lines.findIndex((line, index) => index > markerRow && index < firstOption && LIST_HEADING.test(line));
    const tableEnd = listHeading >= 0 ? listHeading : firstOption;
    const candidateHeaders = lines.slice(1, markerRow);
    const candidateCells = lines.slice(markerRow, tableEnd);
    if (candidateCells.length >= candidateHeaders.length) {
      headers = candidateHeaders;
      rawCells = candidateCells;
    } else {
      headers = lines.slice(1, 4);
      rawCells = lines.slice(4, tableEnd);
    }
  }
  if (headers.length < 2 || rawCells.length < headers.length || rawCells.length % headers.length !== 0) return null;

  const cells = rawCells.map((text): TableGapCell => {
    const marker = gapMarker(text);
    return marker ? { text: "", marker } : { text };
  });
  const parsedMarkers = cells.flatMap((cell) => cell.marker ? [cell.marker] : []);
  if (parsedMarkers.length < 1 || new Set(parsedMarkers).size !== parsedMarkers.length) return null;
  const markers = parsedMarkers;

  const rows = Array.from({ length: rawCells.length / headers.length }, (_, index) => (
    cells.slice(index * headers.length, (index + 1) * headers.length)
  ));
  const options = parseOptions(lines);
  if (options.length < markers.length || new Set(options.map((option) => option.marker)).size !== options.length) return null;

  const allowReuse = metadata?.allow_reuse
    ?? (/(?:цифры|элементы|ответы)\s+в\s+ответе\s+могут\s+повторяться|могут\s+повторяться/iu.test(prompt)
      || options.length < markers.length);
  return { headers, rows, markers, options, allowReuse };
}

export function isCompleteTableGapAnswer(matching: TableGapPrompt, answer: unknown): boolean {
  if (typeof answer !== "string" || [...answer].length !== matching.markers.length) return false;
  const values = [...answer];
  const allowed = new Set(matching.options.map((option) => option.marker));
  return values.every((value) => allowed.has(value)) && (matching.allowReuse || new Set(values).size === values.length);
}

export type TableGapCell = { text: string; marker?: string };

export type TableGapPrompt = {
  headers: string[];
  rows: TableGapCell[][];
  markers: string[];
  options: Array<{ marker: string; label: string }>;
};

const GAP = /^\(([А-ЯЁ])\)$/u;
const OPTION = /^(\d)\)\s*(.+?)\s*[;.]?$/u;

export function parseTableGapPrompt(prompt: string): TableGapPrompt | null {
  const lines = prompt.split(/\n+/u).map((line) => line.trim()).filter(Boolean);
  const optionsHeading = lines.findIndex((line) => /^Пропущенные элементы:/iu.test(line));
  if (optionsHeading < 7) return null;

  const headers = lines.slice(1, 4);
  const rawCells = lines.slice(4, optionsHeading);
  if (headers.length !== 3 || rawCells.length < 6 || rawCells.length % headers.length !== 0) return null;

  const cells = rawCells.map((text): TableGapCell => {
    const gap = GAP.exec(text);
    return gap ? { text: "", marker: gap[1] } : { text };
  });
  const markers = cells.flatMap((cell) => cell.marker ? [cell.marker] : []);
  if (markers.length < 2 || new Set(markers).size !== markers.length) return null;

  const rows = Array.from({ length: rawCells.length / headers.length }, (_, index) => (
    cells.slice(index * headers.length, (index + 1) * headers.length)
  ));
  const options = lines.slice(optionsHeading + 1).flatMap((line) => {
    const option = OPTION.exec(line);
    return option ? [{ marker: option[1], label: option[2].trim() }] : [];
  });
  if (options.length < markers.length || new Set(options.map((option) => option.marker)).size !== options.length) return null;

  return { headers, rows, markers, options };
}

export function isCompleteTableGapAnswer(matching: TableGapPrompt, answer: unknown): boolean {
  if (typeof answer !== "string" || answer.length !== matching.markers.length) return false;
  const values = [...answer];
  const allowed = new Set(matching.options.map((option) => option.marker));
  return values.every((value) => allowed.has(value)) && new Set(values).size === values.length;
}

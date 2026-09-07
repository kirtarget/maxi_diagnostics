import { FormattedMathText } from "./math-display";

// Source tables arrive as normalized rows. Keep explicit headers and body rows
// separate so the desktop grid and responsive card view share one data shape.
export function PromptTable({ headerRows, rows, columns, subject }: { headerRows: string[][]; rows: string[][]; columns: number; subject?: string }) {
  const width = Math.max(columns, ...headerRows.map((row) => row.length), ...rows.map((row) => row.length));
  const normalizedHeaders = headerRows.map((header) => [...header, ...Array(Math.max(0, width - header.length)).fill("")]);
  const normalizedBody = rows.map((row) => [...row, ...Array(Math.max(0, width - row.length)).fill("")]);
  const headerOnly = normalizedBody.length === 0 && normalizedHeaders.length === 1;
  const cardHeader = headerOnly ? [] : normalizedHeaders.at(-1) ?? [];
  const cardRows = normalizedBody.length > 0
    ? normalizedBody
    : headerOnly
      ? [normalizedHeaders[0]]
      : [];
  return (
    <div className="question-table-scroll" data-columns={width}>
      <table className="question-table">
        {normalizedHeaders.length > 0 && <thead>
          {normalizedHeaders.map((header, rowIndex) => (
            <tr key={rowIndex}>
              {header.map((cell, cellIndex) => (
                <th key={cellIndex} scope="col"><FormattedMathText text={cell} subject={subject} /></th>
              ))}
            </tr>
          ))}
        </thead>}
        <tbody>
          {normalizedBody.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}><FormattedMathText text={cell} subject={subject} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="question-table-cards" aria-label="Строки таблицы">
        {cardRows.map((row, rowIndex) => (
          <div className="question-table-card" key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <div className="question-table-card-cell" key={cellIndex}>
                {cardHeader[cellIndex] && <span className="question-table-card-label"><FormattedMathText text={cardHeader[cellIndex]} subject={subject} /></span>}
                <span className="question-table-card-value"><FormattedMathText text={cell} subject={subject} /></span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

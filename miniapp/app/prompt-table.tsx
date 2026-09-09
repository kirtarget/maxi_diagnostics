import { FormattedMathText } from "./math-display";

// A cell this long holds a sentence, not a grid value. Such a table cannot keep a
// readable column width on a phone, so it is stacked instead of scrolled.
const PROSE_CELL_LENGTH = 60;

// Source tables arrive as normalized rows. Keep explicit headers and body rows
// separate so the desktop grid and responsive card view share one data shape.
export function PromptTable({ headerRows, rows, columns, subject }: { headerRows: string[][]; rows: string[][]; columns: number; subject?: string }) {
  const width = Math.max(columns, ...headerRows.map((row) => row.length), ...rows.map((row) => row.length));
  const normalizedHeaders = headerRows.map((header) => [...header, ...Array(Math.max(0, width - header.length)).fill("")]);
  const normalizedBody = rows.map((row) => [...row, ...Array(Math.max(0, width - row.length)).fill("")]);
  // Headings with nothing under them are the paper answer form, not a data table.
  if (normalizedBody.length === 0 && normalizedHeaders.length === 1) {
    return <PromptBlank cells={normalizedHeaders[0]} subject={subject} />;
  }
  const cardHeader = normalizedHeaders.at(-1) ?? [];
  const prose = [...normalizedHeaders, ...normalizedBody]
    .some((row) => row.some((cell) => cell.length > PROSE_CELL_LENGTH));
  return (
    <div
      className="question-table-scroll"
      data-columns={width}
      data-layout={prose ? "prose" : "grid"}
      tabIndex={prose ? undefined : 0}
      role={prose ? undefined : "region"}
      aria-label={prose ? undefined : "Таблица, прокручивается по горизонтали"}
    >
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
        {normalizedBody.map((row, rowIndex) => (
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

// The blank names each answer slot, which is what fixes the order of the digits.
export function PromptBlank({ cells, subject }: { cells: string[]; subject?: string }) {
  return (
    <div className="prompt-blank" role="group" aria-label="Поля ответа">
      {cells.map((cell, index) => (
        <div className="prompt-blank-cell" key={index}>
          <span className="prompt-blank-label"><FormattedMathText text={cell} subject={subject} /></span>
          <span className="prompt-blank-slot" aria-hidden="true">—</span>
        </div>
      ))}
    </div>
  );
}

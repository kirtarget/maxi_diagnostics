import { FormattedMathText } from "./math-display";

// The converter flattens a source table to one `cell | cell` line per row. Read
// as prose that is a wall of vertical bars, so both the question and its review
// draw the grid the author wrote.
export function PromptTable({ rows }: { rows: string[][] }) {
  const [header, ...body] = rows;
  return (
    <div className="question-table-scroll">
      <table className="question-table">
        <thead>
          <tr>
            {header.map((cell, cellIndex) => (
              <th key={cellIndex} scope="col"><FormattedMathText text={cell} /></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <td key={cellIndex}><FormattedMathText text={cell} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

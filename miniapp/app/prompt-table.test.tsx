import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PromptTable } from "./prompt-table";

describe("PromptTable responsive contract", () => {
  it("does not invent a blank thead for headerless rows", () => {
    const html = renderToStaticMarkup(<PromptTable headerRows={[]} rows={[["A", "текст"]]} columns={2} />);
    expect(html).not.toContain("<thead>");
    expect(html).not.toContain('role="row"');
    expect(html).toContain('data-columns="2"');
  });

  it("keeps mobile cards row-shaped and wide tables scrollable", () => {
    const html = renderToStaticMarkup(<PromptTable headerRows={[["Х", "Y"]]} rows={[]} columns={2} />);
    expect(html).toContain('class="question-table-cards"');
    const cards = html.slice(html.indexOf('<div class="question-table-cards"'));
    expect(cards.match(/Х/g)).toHaveLength(1);
    expect(cards.match(/Y/g)).toHaveLength(1);
    expect(cards).not.toContain("question-table-card-label");
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");
    expect(css).toContain(".question-table-scroll[data-columns=\"2\"] .question-table-card {");
    expect(css).toContain(".question-table-scroll:not([data-columns=\"2\"]) .question-table { min-width: 640px; }");
  });
});

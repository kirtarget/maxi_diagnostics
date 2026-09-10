import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PromptTable } from "./prompt-table";

const css = () => readFileSync(new URL("./globals.css", import.meta.url), "utf8");

describe("PromptTable responsive contract", () => {
  it("does not invent a blank thead for headerless rows", () => {
    const html = renderToStaticMarkup(<PromptTable headerRows={[]} rows={[["A", "текст"]]} columns={2} />);
    expect(html).not.toContain("<thead>");
    expect(html).not.toContain('role="row"');
    expect(html).toContain('data-columns="2"');
  });

  it("keeps mobile cards row-shaped for two-column tables", () => {
    const html = renderToStaticMarkup(
      <PromptTable headerRows={[["Металл", "Свойство"]]} rows={[["Железо", "ковкий"]]} columns={2} />,
    );
    expect(html).toContain('class="question-table-cards"');
    const cards = html.slice(html.indexOf('<div class="question-table-cards"'));
    expect(cards.match(/Железо/g)).toHaveLength(1);
    expect(css()).toContain(".question-table-scroll[data-columns=\"2\"] .question-table-card,");
  });

  it("renders headings with nothing under them as an answer blank, not a table", () => {
    const html = renderToStaticMarkup(<PromptTable headerRows={[["Х", "Y"]]} rows={[]} columns={2} />);
    expect(html).not.toContain("<table");
    expect(html).toContain('class="prompt-blank"');
    expect(html.match(/Х/g)).toHaveLength(1);
    expect(html.match(/Y/g)).toHaveLength(1);
  });

  it("stacks tables whose cells hold sentences instead of clipping them", () => {
    const sentence = "In ancient Greece there were many temples built for Apollo, the god of youth and poetry.";
    const html = renderToStaticMarkup(<PromptTable headerRows={[]} rows={[["10", sentence, "GREAT"]]} columns={3} />);
    expect(html).toContain('data-layout="prose"');
    expect(html).toContain("GREAT");
    expect(css()).toContain(".question-table-scroll:not([data-columns=\"2\"]):not([data-layout=\"prose\"]) .question-table { min-width: 640px; }");
    expect(css()).toContain(".question-table-scroll[data-layout=\"prose\"] .question-table { display: none; }");
  });

  it("makes a wide grid table a reachable scroll region with a visible edge cue", () => {
    const html = renderToStaticMarkup(
      <PromptTable headerRows={[["Год", "Двор", "Армия", "Флот"]]} rows={[["1763", "9,5", "45,9", "7,1"]]} columns={4} />,
    );
    expect(html).toContain('data-layout="grid"');
    expect(html).toContain('tabindex="0"');
    expect(html).toContain('role="region"');
    expect(css()).toMatch(/\.question-table-scroll\s*\{[\s\S]*no-repeat scroll,[\s\S]*\}/u);
  });

  it("lets the last column clear the row label on a phone", () => {
    expect(css()).toMatch(/@media\s*\(max-width:\s*479px\)[\s\S]*\.question-table td:first-child\s*\{\s*position:\s*static;/u);
  });
});

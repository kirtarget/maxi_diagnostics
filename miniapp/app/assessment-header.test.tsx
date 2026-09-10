import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AssessmentHeader } from "./assessment-header";

const callbacks = { onBack: vi.fn(), onExit: vi.fn() };

function markup(overrides: Partial<React.ComponentProps<typeof AssessmentHeader>["model"]> = {}) {
  return renderToStaticMarkup(<AssessmentHeader model={{
    topic: "Задание 2 из 4 · Биология",
    current: 2,
    total: 4,
    backDisabled: false,
    progressVariant: "dots",
    percent: 50,
    progressMessage: "Задание 2 из 4. Набираем темп",
    ...callbacks,
    ...overrides,
  }} />);
}

describe("AssessmentHeader", () => {
  it("uses dots for short assessments and exposes one semantic progressbar", () => {
    const html = markup();
    expect(html).toContain("assessment-progress-dots");
    expect(html.match(/role="progressbar"/g)).toHaveLength(1);
    expect(html).toContain('aria-valuetext="Задание 2 из 4. Набираем темп"');
    expect(html.match(/class="question-progress-node/g)).toHaveLength(4);
  });

  it("uses a bar for long assessments and disables the first back control", () => {
    const html = markup({ total: 20, current: 1, progressVariant: "bar", percent: 5, backDisabled: true });
    expect(html).toContain("assessment-progress-bar");
    expect(html).toContain('class="assessment-header-back back-button"');
    expect(html).toContain('disabled=""');
    expect(html).toContain('style="width:5%"');
  });

  it("keeps reference navigation and save feedback reachable", () => {
    const html = markup({ onReference: callbacks.onBack, saveState: "saved", announcement: "Прогресс сохраняется" });
    expect(html).toContain("К тексту ↑");
    expect(html).toContain("Прогресс сохраняется");
    expect(html).toContain('role="status"');
  });

  it("does not present idle or unknown state as an active save", () => {
    expect(markup()).not.toContain("question-save-state");
    expect(markup({ saveState: undefined })).not.toContain("question-save-state");
  });

  it("keeps the shell header and actions within the mobile hit-area contract", () => {
    const css = readFileSync(resolve(fileURLToPath(new URL("./globals.css", import.meta.url))), "utf8");
    expect(css).toMatch(/\.assessment-header\s*\{[^}]*height:\s*56px/s);
    expect(css).toMatch(/\.assessment-header button:not\(\.question-progress-node\)\s*\{[^}]*min-width:\s*44px/s);
    expect(css).toMatch(/\.assessment-header button:not\(\.question-progress-node\)\s*\{[^}]*min-height:\s*44px/s);
    expect(css).toMatch(/\.question-action-bar\s*\{[^}]*position:\s*fixed/s);
  });

  it("keeps a jump node the same 6px segment as a plain one", () => {
    const css = readFileSync(resolve(fileURLToPath(new URL("./globals.css", import.meta.url))), "utf8");
    // The header 44px target must skip the rail nodes, or each segment renders as a 44px circle.
    expect(css).not.toMatch(/\.assessment-header button\s*\{/s);
    expect(css).toMatch(/\.question-progress-node\s*\{[^}]*height:\s*6px/s);
    // The tap area lives on ::after, and the rail must not clip it away.
    expect(css).toMatch(/\.question-progress-jump::after\s*\{[^}]*inset:\s*-19px/s);
    expect(css).toMatch(/\.question-progress-rail\.assessment-progress-dots\s*\{[^}]*overflow:\s*visible/s);
    // A jump node carries no size of its own, so it inherits the plain node geometry.
    const jump = css.match(/\.question-progress-jump\s*\{([^}]*)\}/s)?.[1] ?? "";
    expect(jump).not.toMatch(/min-height|min-width|height:/);
  });
});

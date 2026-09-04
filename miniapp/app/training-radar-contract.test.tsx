import { readFileSync } from "node:fs";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WelcomeScreen } from "./navigation-screens";
import type { Brand, PublicDiagnostic } from "./types";

const question = (id: string) => ({
  id,
  type: "single" as const,
  topic: "Тема",
  title: `Задание ${id}`,
  prompt: "Условие",
  options: [{ id: "a", label: "Ответ" }],
});

describe("Training Radar UI contracts", () => {
  it("derives its question range from a catalog whose maximum is below 20", () => {
    const diagnostics: PublicDiagnostic[] = [{
      id: "demo",
      content_version: "v1",
      exam: "ОГЭ",
      subject: "Математика",
      mark: "М",
      quick_count: 3,
      full_count: 7,
      question_count: 7,
      questions: Array.from({ length: 7 }, (_, index) => question(String(index + 1))),
    }];
    const html = renderToStaticMarkup(
      <WelcomeScreen
        diagnostics={diagnostics}
        labels={{
          start_diagnostic: "Начать диагностику",
          privacy_label: "Конфиденциальность",
          support_label: "Поддержка",
        } as Brand["interface"]}
        links={{ website: "https://school.example", support: "https://school.example/support", privacy: "https://school.example/privacy", offers: [] }}
        onStart={() => undefined}
      />,
    );

    expect(html).toContain("3–7");
    expect(html).toContain("Без таймера");
    expect(html).not.toContain(">20<");
    expect(html).not.toContain("≈10");
  });

  it("keeps table-gap selects at least 44px tall", () => {
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");
    expect(css).toMatch(/\.table-gap-select select\s*\{[^}]*min-height:\s*44px/u);
  });
});

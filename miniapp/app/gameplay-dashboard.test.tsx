import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SubjectsScreen, WelcomeScreen } from "./navigation-screens";

describe("onboarding screens", () => {
  const diagnostics = [{
    id: "math",
    content_version: "v1",
    exam: "ОГЭ",
    subject: "Математика",
    mark: "М",
    quick_count: 3,
    full_count: 12,
    question_count: 12,
  }];

  it("advertises only the quick diagnostic range during onboarding", () => {
    const html = renderToStaticMarkup(<WelcomeScreen
      diagnostics={[...diagnostics, { ...diagnostics[0], id: "second", quick_count: 2, full_count: 26 }]}
      labels={{} as never} links={{ privacy: "#", support: "#" } as never} onStart={() => undefined}
    />);
    expect(html).toContain("2–3");
    expect(html).not.toContain("2–26");
  });

  it.each([[1, "задание"], [2, "задания"], [3, "задания"], [5, "заданий"], [11, "заданий"]])("declines %s questions and describes answer review", (count, word) => {
    const html = renderToStaticMarkup(<SubjectsScreen
      diagnostics={[{ ...diagnostics[0], quick_count: count as number }]}
      exam="ОГЭ" labels={{} as never} mode="quick" onBack={() => undefined}
      onExam={() => undefined} onSelect={() => undefined}
    />);
    expect(html).toContain(`${count} ${word} · разбор ответов`);
    expect(html).not.toContain("полный разбор");
  });
});

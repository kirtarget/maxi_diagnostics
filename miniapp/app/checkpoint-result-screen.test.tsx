// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";
import { act } from "react";

import { CheckpointResultScreen } from "./checkpoint-result-screen";
import type { CheckpointRecordResponse } from "./types";

function record(overrides: Partial<CheckpointRecordResponse> = {}): CheckpointRecordResponse {
  return {
    ok: true,
    passed: true,
    unit_index: 0,
    mastered_count: 4,
    question_total: 5,
    checkpoint: null,
    checkpoints: [],
    ...overrides,
  };
}

describe("CheckpointResultScreen", () => {
  it("shows a pass with the срез tally as a count and a path CTA", () => {
    const html = renderToStaticMarkup(<CheckpointResultScreen result={record()} onViewPath={vi.fn()} onHome={vi.fn()} />);
    expect(html).toContain("Чекпоинт пройден");
    expect(html).toContain("4 из 5");
    expect(html).toContain("Смотреть путь");
    // No accuracy percent on the checkpoint result.
    expect(html).not.toContain("%");
    expect(html).toContain("is-passed");
  });

  it("shows a retry state below the pass threshold", () => {
    const html = renderToStaticMarkup(<CheckpointResultScreen result={record({ passed: false, mastered_count: 2 })} onViewPath={vi.fn()} onHome={vi.fn()} />);
    expect(html).toContain("Чекпоинт не пройден");
    expect(html).toContain("2 из 5");
    expect(html).toContain("Вернуться к занятиям");
    expect(html).toContain("is-retry");
  });

  it("keeps the срез tally in the genitive for 1, 2 and 5", () => {
    const one = renderToStaticMarkup(<CheckpointResultScreen result={record({ mastered_count: 0, question_total: 1 })} onViewPath={vi.fn()} onHome={vi.fn()} />);
    expect(one).toContain("0 из 1 задания закрыто");
    const two = renderToStaticMarkup(<CheckpointResultScreen result={record({ mastered_count: 1, question_total: 2 })} onViewPath={vi.fn()} onHome={vi.fn()} />);
    expect(two).toContain("1 из 2 заданий закрыто");
    const five = renderToStaticMarkup(<CheckpointResultScreen result={record({ mastered_count: 4, question_total: 5 })} onViewPath={vi.fn()} onHome={vi.fn()} />);
    expect(five).toContain("4 из 5 заданий закрыто");
  });

  it("routes a passed result to the path", () => {
    const onViewPath = vi.fn();
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => { root.render(<CheckpointResultScreen result={record()} onViewPath={onViewPath} onHome={vi.fn()} />); });
    const button = Array.from(container.querySelectorAll("button")).find((el) => el.textContent?.includes("Смотреть путь"));
    act(() => { button!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(onViewPath).toHaveBeenCalledTimes(1);
    act(() => { root.unmount(); });
  });
});
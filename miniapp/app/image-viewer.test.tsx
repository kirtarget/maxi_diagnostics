// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it, beforeEach, afterEach } from "vitest";

import { ImageViewer } from "./image-viewer";
import { QuestionView } from "./question-screen";
import type { Brand, Question } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function renderViewer(props: Partial<React.ComponentProps<typeof ImageViewer>> = {}) {
  await act(async () => {
    root.render(<ImageViewer assets={[{ path: "assets/questions/demo.png" }]} fallbackAlt="Иллюстрация" {...props} />);
  });
}

function css(): string {
  return readFileSync("app/globals.css", "utf8");
}

function catalogQuestion(path: string, id: string): Question {
  const catalog = JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8")) as { questions: Array<Record<string, unknown>> };
  const raw = catalog.questions.find((question) => question.id === id);
  if (!raw) throw new Error(`Missing catalog question ${id}`);
  const { correct: _serverOnly, ...publicQuestion } = raw;
  return publicQuestion as Question;
}

const labels = {
  back: "Назад",
  task_label: "Задание",
  of_label: "из",
  illustration_alt: "Иллюстрация к заданию",
  next_question: "Следующее задание",
  get_result: "Получить результат",
  answer_label: "Ваш ответ",
  enter_answer: "Введите ответ",
  choose_option: "Выберите вариант",
} as unknown as Brand["interface"];

describe("ImageViewer", () => {
  it("drops unsafe assets and numbers fallback alt text", () => {
    const html = renderToStaticMarkup(
      <ImageViewer
        assets={[
          { path: "assets/questions/first.png" },
          { path: "../private.png" },
          { path: "assets/questions/second.png" },
        ]}
        fallbackAlt="Иллюстрация к заданию"
      />,
    );
    expect(html).toContain('src="/assets/questions/first.png" alt="Иллюстрация к заданию 1"');
    expect(html).toContain('src="/assets/questions/second.png" alt="Иллюстрация к заданию 2"');
    expect(html).not.toContain("private.png");
    expect(html).toContain("Нажми, чтобы увеличить");
  });

  it("prefers explicit asset_alt and keeps dialog semantics", async () => {
    await renderViewer({ assets: [{ path: "assets/questions/demo.png", alt: "Схема реакции" }] });
    const trigger = container.querySelector(".image-viewer-trigger") as HTMLButtonElement;
    expect(trigger.getAttribute("aria-label")).toContain("Схема реакции");
    await act(async () => trigger.click());
    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog?.getAttribute("aria-modal")).toBe("true");
    expect(container.querySelectorAll('[role="dialog"]').length).toBe(1);
    expect((dialog?.querySelector("img") as HTMLImageElement).alt).toBe("Схема реакции");
  });

  it("closes with Escape and restores focus to the trigger", async () => {
    await renderViewer();
    const trigger = container.querySelector(".image-viewer-trigger") as HTMLButtonElement;
    trigger.focus();
    await act(async () => trigger.click());
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Закрыть изображение");
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("provides bounded keyboard zoom controls", async () => {
    await renderViewer();
    await act(async () => (container.querySelector(".image-viewer-trigger") as HTMLButtonElement).click());
    const decrease = container.querySelector('[aria-label="Уменьшить"]') as HTMLButtonElement;
    const increase = container.querySelector('[aria-label="Увеличить"]') as HTMLButtonElement;
    expect(decrease.disabled).toBe(true);
    for (let index = 0; index < 10; index += 1) {
      await act(async () => increase.click());
    }
    expect(increase.disabled).toBe(true);
    expect(container.querySelector(".image-viewer-zoom-controls")?.textContent).toContain("300%");
    await act(async () => decrease.click());
    expect(increase.disabled).toBe(false);
  });

  it("keeps intrinsic raster size, mobile height, horizontal overflow, and native pinch contract", () => {
    const styles = css();
    expect(styles).toMatch(/\.image-viewer-inline\s*\{[\s\S]*?width:\s*auto;[\s\S]*?max-width:\s*none;[\s\S]*?max-height:\s*40vh;/);
    expect(styles).toMatch(/\.image-viewer-item\s*\{[\s\S]*?overflow-x:\s*auto;/);
    expect(styles).toMatch(/\.image-viewer-dialog-viewport\s*\{[\s\S]*?touch-action:\s*pan-x pan-y pinch-zoom;/);
    expect(styles).toMatch(/\.image-viewer-dialog-viewport\s*\{[\s\S]*?align-items:\s*flex-start;[\s\S]*?justify-content:\s*flex-start;/);
    expect(styles).toMatch(/\.image-viewer-dialog-image\s*\{[\s\S]*?transform-origin:\s*top left;/);
    expect(styles).toMatch(/\.image-viewer-close,[\s\S]*?\.image-viewer-zoom-control\s*\{[\s\S]*?min-width:\s*44px;[\s\S]*?min-height:\s*44px;/);
    const html = renderToStaticMarkup(<ImageViewer assets={[{ path: "assets/questions/wide.png" }]} fallbackAlt="Иллюстрация" />);
    expect(html).toContain('class="image-viewer-inline"');
    expect(html).toContain('class="image-viewer-item"');
  });

  it("accepts the real q05 and q09 raster dimensions without client-side upscaling", () => {
    const pngSize = (path: string): [number, number] => {
      const bytes = readFileSync(new URL(path, import.meta.url));
      const uint = (offset: number) => bytes.readUInt32BE(offset);
      return [uint(16), uint(20)];
    };
    expect(pngSize("../../school/assets/questions/sp-mathematics-oge-2022-q5-1.png")).toEqual([900, 230]);
    expect(pngSize("../../school/assets/questions/sp-biology-ege-2022-q9-1.png")).toEqual([113, 224]);
    const html = renderToStaticMarkup(
      <ImageViewer
        assets={[{ path: "assets/questions/sp-mathematics-oge-2022-q5-1.png" }, { path: "assets/questions/sp-biology-ege-2022-q9-1.png" }]}
        fallbackAlt="Иллюстрация к заданию"
      />,
    );
    expect(html).toContain("sp-mathematics-oge-2022-q5-1.png");
    expect(html).toContain("sp-biology-ege-2022-q9-1.png");
    expect(html.match(/image-viewer-inline/g)?.length).toBe(2);
  });

  it("keeps real q09 answer content after the non-upscaled image and exposes q05 through the same viewer", () => {
    const q05 = catalogQuestion("../../school/diagnostics/oge-mathematics-198.json", "sp-mathematics-oge-2022-q5");
    const q09 = catalogQuestion("../../school/diagnostics/ege-biology-1207.json", "sp-biology-ege-2022-q9");
    const q05Html = renderToStaticMarkup(
      <QuestionView question={q05} index={0} total={1} answer={undefined} labels={labels} onAnswer={() => undefined} onBack={() => undefined} onNext={() => undefined} />,
    );
    const q09Html = renderToStaticMarkup(
      <QuestionView question={q09} index={0} total={1} answer={undefined} labels={labels} onAnswer={() => undefined} onBack={() => undefined} onNext={() => undefined} />,
    );
    expect(q05Html).toContain("sp-mathematics-oge-2022-q5-1.png");
    expect(q05Html).toContain("image-viewer-hint");
    expect(q09Html).toContain("sp-biology-ege-2022-q9-1.png");
    const firstOption = (q09 as Extract<Question, { type: "multiple" }>).options[0]?.label;
    expect(firstOption).toBeTruthy();
    expect(q09Html.indexOf("sp-biology-ege-2022-q9-1.png")).toBeLessThan(q09Html.indexOf(String(firstOption)));
  });

  it("traps Tab and Shift+Tab inside the fullscreen dialog", async () => {
    await renderViewer();
    await act(async () => (container.querySelector(".image-viewer-trigger") as HTMLButtonElement).click());
    const buttons = Array.from(container.querySelectorAll(".image-viewer-dialog button")) as HTMLButtonElement[];
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    last.focus();
    const forward = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    await act(async () => document.dispatchEvent(forward));
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);
    first.focus();
    const backward = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    await act(async () => document.dispatchEvent(backward));
    expect(backward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(last);
  });
});

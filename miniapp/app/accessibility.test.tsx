// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { AnswerEditor } from "./answer-editor";
import { MatchingAnswer, type MatchingModel } from "./matching-answer";
import type { Question } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const single: Question = {
  id: "access-single",
  type: "single",
  topic: "Алгебра",
  title: "Задание 1",
  prompt: "Выбери ответ.",
  options: [{ id: "a", label: "Первый" }, { id: "b", label: "Второй" }, { id: "c", label: "Третий" }],
};

const multiple: Question = {
  ...single,
  id: "access-multiple",
  type: "multiple",
  selection_limit: 2,
};

const matchingModel: MatchingModel = {
  source: "matching",
  rows: [{ key: "i1", marker: "А", label: "Первый пункт" }],
  options: [{ key: "o1", marker: "1", label: "Первый" }, { key: "o2", marker: "2", label: "Второй" }],
  markers: ["А"],
  answerLength: 1,
  allowReuse: true,
};

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

describe("accessibility selection contracts", () => {
  it("moves a single-choice radio with Arrow keys and preserves roving tab order", async () => {
    const onChange = vi.fn();
    await act(async () => root.render(<AnswerEditor question={single} value="b" onChange={onChange} />));
    const radios = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    expect(radios.map((radio) => radio.tabIndex)).toEqual([-1, 0, -1]);

    radios[1].focus();
    await act(async () => radios[1].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })));
    expect(onChange).toHaveBeenCalledWith("a");
    expect(document.activeElement).toBe(radios[0]);
  });

  it("exposes multiple choice as checkboxes with one stable selected-count description", async () => {
    await act(async () => root.render(<AnswerEditor question={multiple} value={["a"]} onChange={vi.fn()} />));
    const checkboxes = [...container.querySelectorAll<HTMLElement>('[role="checkbox"]')];
    expect(checkboxes).toHaveLength(3);
    expect(checkboxes.every((control) => control.getAttribute("aria-describedby") === "multiple-selection-count-access-multiple")).toBe(true);
    expect(container.querySelectorAll("[aria-live]")).toHaveLength(0);
    expect(container.querySelector("#multiple-selection-count-access-multiple")?.textContent).toBe("Выбрано 1 из 2");
  });

  it("moves matching and sequence radio palettes with Arrow keys", async () => {
    const matchingChange = vi.fn();
    await act(async () => root.render(<MatchingAnswer model={matchingModel} value={{}} onChange={matchingChange} />));
    const matchingRadios = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    expect(matchingRadios.map((radio) => radio.tabIndex)).toEqual([0, -1]);
    matchingRadios[0].focus();
    await act(async () => matchingRadios[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(matchingChange).toHaveBeenCalledWith({ i1: "o2" });
    expect(document.activeElement).toBe(matchingRadios[1]);

    const sequenceModel: MatchingModel = { ...matchingModel, source: "sequence", rows: [{ key: "А", marker: "А", label: "Первый пункт" }] };
    const sequenceChange = vi.fn();
    await act(async () => root.render(<MatchingAnswer model={sequenceModel} value="" onChange={sequenceChange} />));
    const sequenceRadios = [...container.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    sequenceRadios[0].focus();
    await act(async () => sequenceRadios[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(sequenceChange).toHaveBeenCalledWith("2");
    expect(document.activeElement).toBe(sequenceRadios[1]);
  });
});

describe("accessibility CSS contracts", () => {
  it("keeps the audit tokens, focus boundary, control sizing, and preview marker contract", () => {
    const css = readFileSync("app/globals.css", "utf8");
    expect(css).toContain("--faint: color-mix(in srgb, var(--brand-ink) 62%, white);");
    expect(css).toContain("--decor-line: color-mix(in srgb, var(--brand-ink) 12%, transparent);");
    expect(css).toContain("--control-line: color-mix(in srgb, var(--brand-ink) 38%, white);");
    expect(css).toContain("--interactive-line: color-mix(in srgb, var(--brand-ink) 55%, white);");
    expect(css).toMatch(/outline-width:\s*3px;\s*outline-style:\s*solid;\s*outline-color:\s*var\(--brand-primary\);\s*outline-offset:\s*2px/u);
    expect(css).toMatch(/\.table-gap-select select\s*\{[\s\S]*font-size:\s*16px;/u);
    expect(css).toMatch(/\.matching-answer-preview small\s*\{[\s\S]*font-size:\s*11px;/u);
    expect(css).toMatch(/button:disabled,[\s\S]*color:\s*var\(--muted\);[\s\S]*border-style:\s*dashed;/u);
    const style = document.createElement("style");
    const primary = css.match(/--brand-primary:\s*(#[0-9a-f]+)/iu)?.[1] ?? "#5a34e0";
    style.textContent = `${css.replaceAll(":focus-visible", ":focus").replaceAll("var(--brand-primary)", primary)}
.focus-contract:focus { outline: 3px solid ${primary}; outline-offset: 2px; }`;
    document.head.appendChild(style);
    expect(getComputedStyle(document.documentElement).getPropertyValue("--faint")).toContain("62%");
    style.remove();
  });

  it("verifies the primary focus boundary clears the three-to-one contrast floor", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const token = (name: string) => css.match(new RegExp(`--${name}:\\s*(#[0-9a-f]+)`, "iu"))?.[1] ?? "";
    const contrast = (foreground: string, background: string) => {
      const luminance = (color: string) => {
        const channels = color.match(/[0-9a-f]{2}/giu)?.map((part) => Number.parseInt(part, 16) / 255) ?? [];
        const linear = channels.map((channel) => channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
        return 0.2126 * (linear[0] ?? 0) + 0.7152 * (linear[1] ?? 0) + 0.0722 * (linear[2] ?? 0);
      };
      const light = Math.max(luminance(foreground), luminance(background));
      const dark = Math.min(luminance(foreground), luminance(background));
      return (light + 0.05) / (dark + 0.05);
    };
    const mixWithWhite = (ink: string, percentage: number) => {
      const channels = ink.match(/[0-9a-f]{2}/giu)?.map((part) => Number.parseInt(part, 16)) ?? [];
      return `#${channels.map((channel) => Math.round(channel * percentage + 255 * (1 - percentage)).toString(16).padStart(2, "0")).join("")}`;
    };
    const ink = token("brand-ink");
    const paper = token("brand-paper");
    const background = token("brand-background");
    const primary = token("brand-primary");
    const faint = mixWithWhite(ink, 0.62);
    const interactive = mixWithWhite(ink, 0.55);
    expect(contrast(faint, paper)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(faint, background)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(interactive, paper)).toBeGreaterThanOrEqual(3);
    expect(contrast(interactive, background)).toBeGreaterThanOrEqual(3);
    expect(contrast(primary, paper)).toBeGreaterThanOrEqual(3);
    expect(contrast(primary, background)).toBeGreaterThanOrEqual(3);
  });

  it("keeps the visible focus outline after control-specific rules", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const ruleBody = (selector: RegExp) => {
      const match = css.match(selector);
      expect(match).not.toBeNull();
      return match?.[1] ?? "";
    };
    const suppressesOutline = /outline(?:-style)?\s*:\s*(?:none|0(?:[a-z%]+)?)/iu;
    expect(ruleBody(/\.short-answer-control input,\s*\.short-answer > input\s*\{([^}]*)\}/u)).not.toMatch(suppressesOutline);
    expect(ruleBody(/\.table-gap-select select\s*\{([^}]*)\}/u)).not.toMatch(suppressesOutline);
    const style = document.createElement("style");
    // jsdom does not model keyboard modality for :focus-visible. Replacing the
    // pseudo-class keeps the production cascade and makes the computed check deterministic.
    style.textContent = css.replaceAll(":focus-visible", ":focus").replaceAll("var(--brand-primary)", "#5a34e0");
    document.head.appendChild(style);
    const input = document.createElement("input");
    input.className = "focus-contract";
    const wrapper = document.createElement("div");
    wrapper.className = "short-answer-control";
    wrapper.appendChild(input);
    document.body.appendChild(wrapper);
    input.focus();
    const inputFocus = getComputedStyle(input);
    expect(inputFocus.outlineWidth).toBe("3px");
    expect(inputFocus.outlineStyle).toBe("solid");
    expect(inputFocus.outlineColor).toMatch(/rgb\(90, 52, 224\)|#5a34e0/iu);
    expect(inputFocus.outlineOffset).toBe("2px");
    const select = document.createElement("select");
    select.className = "focus-contract";
    const selectWrapper = document.createElement("label");
    selectWrapper.className = "table-gap-select";
    selectWrapper.appendChild(select);
    document.body.appendChild(selectWrapper);
    select.focus();
    const selectFocus = getComputedStyle(select);
    expect(selectFocus.outlineWidth).toBe("3px");
    expect(selectFocus.outlineStyle).toBe("solid");
    expect(selectFocus.outlineColor).toMatch(/rgb\(90, 52, 224\)|#5a34e0/iu);
    expect(selectFocus.outlineOffset).toBe("2px");
    wrapper.remove();
    selectWrapper.remove();
    style.remove();
  });
});

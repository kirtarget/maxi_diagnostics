import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The audit measured colours by hand and the numbers drifted between reports.
 * This gate reads the shipped tokens instead, so a token edit that drops a
 * surface below its WCAG floor fails here rather than in the next audit.
 */

type Rgb = [number, number, number];

const css = readFileSync("app/globals.css", "utf8");

const tokens = new Map<string, string>(
  [...(css.match(/:root\s*\{([\s\S]*?)\n\}/u)?.[1] ?? "").matchAll(/(--[\w-]+):\s*([^;]+);/gu)]
    .map((match) => [match[1], match[2].trim()]),
);

/** Split on commas that sit outside nested parentheses. */
function topLevelParts(input: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    if (char === "(") depth += 1;
    else if (char === ")") depth -= 1;
    else if (char === "," && depth === 0) {
      parts.push(input.slice(start, index));
      start = index + 1;
    }
  }
  parts.push(input.slice(start));
  return parts.map((part) => part.trim());
}

/** Resolve a token expression to opaque RGB, compositing `transparent` over `backdrop`. */
function resolve(expression: string, backdrop: Rgb = [255, 255, 255]): Rgb {
  const value = expression.trim();
  if (value === "transparent") return backdrop;
  if (value === "white") return [255, 255, 255];
  if (value === "black") return [0, 0, 0];

  const hex = value.match(/^#([0-9a-f]{6})$/iu)?.[1];
  if (hex) return [0, 2, 4].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16)) as Rgb;

  const variable = value.match(/^var\((--[\w-]+)\)$/u)?.[1];
  if (variable) {
    const referenced = tokens.get(variable);
    if (!referenced) throw new Error(`unknown token ${variable}`);
    return resolve(referenced, backdrop);
  }

  const mix = value.match(/^color-mix\(in srgb,([\s\S]+)\)$/u)?.[1];
  if (mix) {
    const [first, second] = topLevelParts(mix);
    const share = Number.parseFloat(first.match(/([\d.]+)%\s*$/u)?.[1] ?? "") / 100;
    if (!Number.isFinite(share)) throw new Error(`no percentage in ${first}`);
    const front = resolve(first.replace(/[\d.]+%\s*$/u, ""), backdrop);
    const back = resolve(second, backdrop);
    return front.map((channel, index) => Math.round(channel * share + back[index] * (1 - share))) as Rgb;
  }

  throw new Error(`cannot resolve ${value}`);
}

function luminance(color: Rgb): number {
  const [r, g, b] = color.map((channel) => {
    const ratio = channel / 255;
    return ratio <= 0.03928 ? ratio / 12.92 : ((ratio + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(foreground: Rgb, background: Rgb): number {
  const light = Math.max(luminance(foreground), luminance(background));
  const dark = Math.min(luminance(foreground), luminance(background));
  return (light + 0.05) / (dark + 0.05);
}

/** Each row names a surface a student actually looks at, and the WCAG floor it owes. */
const contract: Array<{ what: string; ink: string; on: string; over?: string; floor: number }> = [
  { what: "helper text on paper", ink: "var(--faint)", on: "var(--brand-paper)", floor: 4.5 },
  { what: "helper text on the app background", ink: "var(--faint)", on: "var(--brand-background)", floor: 4.5 },
  { what: "muted text on paper", ink: "var(--muted)", on: "var(--brand-paper)", floor: 4.5 },
  { what: "unselected option ring on paper", ink: "var(--interactive-line)", on: "var(--brand-paper)", floor: 3 },
  { what: "unselected option ring on the app background", ink: "var(--interactive-line)", on: "var(--brand-background)", floor: 3 },
  { what: "focus outline on paper", ink: "var(--brand-primary)", on: "var(--brand-paper)", floor: 3 },
  { what: "focus outline on the app background", ink: "var(--brand-primary)", on: "var(--brand-background)", floor: 3 },
  {
    what: "disabled button label on its own surface",
    ink: "var(--disabled-ink)",
    on: "color-mix(in srgb, var(--brand-ink) 8%, var(--brand-background))",
    floor: 4.5,
  },
  { what: "disabled control label on paper", ink: "var(--disabled-ink)", on: "var(--brand-paper)", floor: 4.5 },
  {
    what: "trainer life warning pill",
    ink: "var(--brand-ink)",
    on: "var(--brand-signal)",
    floor: 4.5,
  },
  {
    what: "trainer life pill on the feedback panel",
    ink: "white",
    on: "color-mix(in srgb, var(--brand-signal) 70%, transparent)",
    over: "var(--brand-ink)",
    floor: 4.5,
  },
  { what: "completed rail node on the header", ink: "var(--brand-accent)", on: "var(--primary-deep)", floor: 3 },
  { what: "current rail node on the header", ink: "white", on: "var(--primary-deep)", floor: 3 },
];

describe("token contrast", () => {
  it.each(contract)("$what clears $floor:1", ({ ink, on, over, floor }) => {
    const backdrop = over ? resolve(over) : undefined;
    const background = resolve(on, backdrop);
    const measured = contrast(resolve(ink, background), background);
    expect(Number(measured.toFixed(2))).toBeGreaterThanOrEqual(floor);
  });

  it("resolves the tokens it measures instead of hard-coded copies", () => {
    expect(resolve("var(--brand-ink)")).toEqual([22, 18, 31]);
    expect(resolve("color-mix(in srgb, var(--brand-ink) 50%, white)")).toEqual([139, 137, 143]);
    expect(resolve("color-mix(in srgb, white 50%, transparent)", [0, 0, 0])).toEqual([128, 128, 128]);
  });
});

describe("accessibility CSS rules that carry the contrast", () => {
  it("routes every disabled label through the disabled token", () => {
    expect(css).toContain("--disabled-ink: color-mix(in srgb, var(--brand-ink) 68%, white);");
    expect(css).toMatch(/button:disabled,\s*input:disabled,\s*select:disabled\s*\{[^}]*color:\s*var\(--disabled-ink\)/u);
    expect(css).toMatch(/\.primary-button:disabled\s*\{[^}]*color:\s*var\(--disabled-ink\)/u);
    expect(css).toMatch(/\.question-action-bar \.question-next:disabled\s*\{[^}]*color:\s*var\(--disabled-ink\)/u);
  });

  // --control-line measures 2.45:1, so it may draw separators but never a control boundary.
  it("draws control boundaries with the token that clears three to one", () => {
    expect(css).toMatch(/\.submit-review-jump\s*\{[^}]*border:\s*1\.5px solid var\(--interactive-line\)/u);
    const controlLineUses = [...css.matchAll(/([^;{}]*)var\(--control-line\)/gu)].map((match) => match[1].trim());
    expect(controlLineUses).toEqual(["border-top: 1px solid", "border: 2px dashed"]);
  });

  it("keeps the life note readable by out-specifying the lime pill rule", () => {
    const limePill = css.match(/\.trainer-feedback small\s*\{([^}]*)\}/u)?.[1] ?? "";
    expect(limePill).toContain("var(--brand-accent)");
    expect(css).toMatch(/\.trainer-feedback small\.trainer-life-note\.is-warning\s*\{[^}]*color:\s*var\(--brand-ink\)/u);
  });
});

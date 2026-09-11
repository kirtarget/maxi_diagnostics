import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// The three KIR-117 wave 2 animations live entirely in CSS, keyed off classes the
// components already set. These checks pin the motion contract so a later edit
// cannot quietly drop the reduced-motion guard or a verdict animation.
const css = readFileSync("app/globals.css", "utf8");

describe("trainer motion", () => {
  it("collapses every animation and transition under prefers-reduced-motion", () => {
    const block = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toContain("animation-duration: 0.01ms !important");
    expect(block).toContain("transition-duration: 0.01ms !important");
  });

  it("animates the correct verdict and its badge", () => {
    expect(css).toContain(".trainer-feedback.is-correct { animation: kir117-correct-glow");
    expect(css).toContain(".trainer-feedback.is-correct strong::before { animation: kir117-pop");
  });

  it("shakes the incorrect verdict without a punishing bounce", () => {
    expect(css).toContain(".trainer-feedback.is-incorrect { animation: kir117-shake");
    expect(css).toContain("@keyframes kir117-shake");
  });

  it("eases the progress fill instead of snapping it", () => {
    expect(css).toContain(".assessment-progress-fill { transition: width");
    expect(css).toContain(".session-mastery-fill");
    expect(css).toContain("@keyframes kir117-grow");
  });

  it("keeps the correct and incorrect motion inside the brand palette", () => {
    // Lime accent for right, coral signal for wrong. No off-brand colour leaks in.
    expect(css).toContain("@keyframes kir117-correct-glow { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand-accent)");
    expect(css).toContain("@keyframes kir117-signal-glow { 0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand-signal)");
  });
});

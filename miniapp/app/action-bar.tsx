"use client";

import { useEffect, useRef } from "react";

/** Below this the shrunken visual viewport is browser rounding, not a keyboard. */
const KEYBOARD_MIN_HEIGHT = 120;

export type ActionBarSkip = {
  label: string;
  caption: string;
  /** Hidden but still occupying space when false, so the bar keeps one height. */
  available: boolean;
  onSkip: () => void;
};

export type ActionBarProps = {
  primaryLabel: string;
  primaryDisabled: boolean;
  onPrimary: () => void;
  /** Single live region: blocking reason, readiness, skip confirmation or a submit error. */
  message: string;
  messageRole?: "status" | "alert";
  skip?: ActionBarSkip;
};

/**
 * Fixed bottom bar with a height that does not depend on answer readiness.
 * Publishes its height as --action-bar-height and lifts itself over the
 * software keyboard, because a fixed element otherwise sits underneath it.
 */
export function ActionBar({ primaryLabel, primaryDisabled, onPrimary, message, messageRole = "status", skip }: ActionBarProps) {
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const root = document.documentElement;
    const publishHeight = () => {
      root.style.setProperty("--action-bar-height", `${Math.round(bar.getBoundingClientRect().height)}px`);
    };
    publishHeight();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(publishHeight);
    observer?.observe(bar);

    const viewport = window.visualViewport;
    const publishKeyboard = () => {
      if (!viewport) return;
      const inset = Math.round(window.innerHeight - viewport.height - viewport.offsetTop);
      // Browsers report a few fractional pixels with no keyboard on screen; moving
      // the bar for those would reintroduce the shift this bar exists to prevent.
      root.style.setProperty("--keyboard-inset", inset >= KEYBOARD_MIN_HEIGHT ? `${inset}px` : "0px");
    };
    publishKeyboard();
    viewport?.addEventListener("resize", publishKeyboard);
    viewport?.addEventListener("scroll", publishKeyboard);
    return () => {
      observer?.disconnect();
      viewport?.removeEventListener("resize", publishKeyboard);
      viewport?.removeEventListener("scroll", publishKeyboard);
      root.style.removeProperty("--action-bar-height");
      root.style.removeProperty("--keyboard-inset");
    };
  }, []);

  return (
    <div className="question-action-bar" ref={barRef}>
      <button className="primary-button question-next" disabled={primaryDisabled} onClick={onPrimary} type="button">
        {primaryLabel}
        <span aria-hidden="true">→</span>
      </button>
      <p
        className="question-announcement"
        role={messageRole}
        aria-live={messageRole === "alert" ? "assertive" : "polite"}
        aria-atomic="true"
      >
        {message}
      </p>
      {skip && (
        <button
          className={`question-skip${skip.available ? "" : " is-reserved"}`}
          onClick={skip.onSkip}
          type="button"
          aria-hidden={skip.available ? undefined : true}
          tabIndex={skip.available ? undefined : -1}
          disabled={!skip.available}
        >
          <span className="question-skip-label">{skip.label}</span>
          <span className="question-skip-caption">{skip.caption}</span>
        </button>
      )}
    </div>
  );
}

// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmSheet } from "./confirm-sheet";

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

async function renderSheet(props: Partial<React.ComponentProps<typeof ConfirmSheet>> = {}) {
  await act(async () => {
    root.render(<ConfirmSheet open onCancel={() => undefined} onConfirm={() => undefined} {...props} />);
  });
}

function pressTab(shiftKey = false): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab", shiftKey });
  document.dispatchEvent(event);
  return event;
}

describe("ConfirmSheet focus management", () => {
  it("moves focus into the sheet when it opens", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();

    await renderSheet();

    expect(document.activeElement?.textContent).toBe("Остаться");
    trigger.remove();
  });

  it("traps Tab and Shift+Tab within the sheet", async () => {
    await renderSheet();
    const buttons = container.querySelectorAll(".confirm-sheet button");
    const first = buttons[0] as HTMLButtonElement;
    const last = buttons[1] as HTMLButtonElement;

    last.focus();
    const forward = pressTab();
    expect(forward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);

    first.focus();
    const backward = pressTab(true);
    expect(backward.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(last);
  });

  it("restores focus on cancel and confirm", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const onCancel = vi.fn();
    await renderSheet({ onCancel });

    await act(async () => {
      (container.querySelector(".secondary-button") as HTMLButtonElement).click();
    });
    expect(document.activeElement).toBe(trigger);
    expect(onCancel).toHaveBeenCalledOnce();

    await act(async () => {
      root.render(<ConfirmSheet open={false} onCancel={onCancel} onConfirm={() => undefined} />);
    });
    trigger.focus();
    await renderSheet({ onConfirm: vi.fn() });
    await act(async () => {
      (container.querySelector(".primary-button") as HTMLButtonElement).click();
    });
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it("restores focus when the open sheet unmounts", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    await renderSheet();

    await act(async () => root.unmount());
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
    container.remove();
    root = createRoot(container);
  });
});

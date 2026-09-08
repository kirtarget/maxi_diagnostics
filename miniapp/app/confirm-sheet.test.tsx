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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
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
    await act(async () => {
      root.render(<ConfirmSheet open={false} onCancel={onCancel} onConfirm={() => undefined} />);
    });
    expect(document.activeElement).toBe(trigger);
    expect(onCancel).toHaveBeenCalledOnce();

    trigger.focus();
    await renderSheet({ onConfirm: vi.fn() });
    await act(async () => {
      (container.querySelector(".primary-button") as HTMLButtonElement).click();
    });
    await act(async () => {
      root.render(<ConfirmSheet open={false} onCancel={onCancel} onConfirm={() => undefined} />);
    });
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it("keeps focus in the open dialog while async confirmation is pending", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const pending = deferred<void>();
    await renderSheet({ onConfirm: () => pending.promise });
    const confirm = container.querySelector<HTMLButtonElement>(".primary-button")!;
    confirm.focus();
    await act(async () => { confirm.click(); });
    expect(document.activeElement).toBe(confirm);
    pending.resolve();
    await act(async () => { await pending.promise; });
    expect(document.activeElement).toBe(confirm);
    await act(async () => {
      root.render(<ConfirmSheet open={false} onCancel={() => undefined} onConfirm={() => undefined} />);
    });
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });

  it("keeps focus in the dialog when async confirmation fails and parent leaves it open", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    await renderSheet({ onConfirm: async () => undefined });
    const confirm = container.querySelector<HTMLButtonElement>(".primary-button")!;
    confirm.focus();
    await act(async () => { confirm.click(); });
    expect(document.activeElement).toBe(confirm);
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
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

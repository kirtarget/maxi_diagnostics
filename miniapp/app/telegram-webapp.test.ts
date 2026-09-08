// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { initializeTelegram, loadTelegramBridge } from "./telegram-webapp";

afterEach(() => {
  document.head.querySelector('script[data-telegram-web-app]')?.remove();
  delete window.Telegram;
});

describe("Telegram bridge hydration boundary", () => {
  it("loads the bridge after the client asks for it and leaves documentElement untouched before load", async () => {
    const before = document.documentElement.getAttribute("style");
    const bridge = loadTelegramBridge();
    const script = document.head.querySelector<HTMLScriptElement>('script[data-telegram-web-app]');
    expect(script?.src).toBe("https://telegram.org/js/telegram-web-app.js?63");
    expect(document.documentElement.getAttribute("style")).toBe(before);

    const ready = vi.fn();
    const expand = vi.fn();
    window.Telegram = { WebApp: {
      initData: "signed",
      ready,
      expand,
      close: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
    } };
    script?.dispatchEvent(new Event("load"));
    await expect(bridge).resolves.toBe(window.Telegram.WebApp);
    expect(document.documentElement.getAttribute("style")).toBe(before);

    expect(initializeTelegram()).toBe(window.Telegram.WebApp);
    expect(ready).toHaveBeenCalledOnce();
    expect(expand).toHaveBeenCalledOnce();
  });

  it("shares one pending request between concurrent callers", async () => {
    const first = loadTelegramBridge();
    const second = loadTelegramBridge();
    expect(second).toBe(first);
    expect(document.head.querySelectorAll('script[data-telegram-web-app]')).toHaveLength(1);
    const script = document.head.querySelector<HTMLScriptElement>('script[data-telegram-web-app]')!;
    window.Telegram = { WebApp: {
      initData: "signed",
      ready: vi.fn(),
      expand: vi.fn(),
      close: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
    } };
    script.dispatchEvent(new Event("load"));
    await expect(first).resolves.toBe(window.Telegram.WebApp);
    await expect(second).resolves.toBe(window.Telegram.WebApp);
  });

  it("rejects a failed request, removes its script, and retries with a fresh request", async () => {
    const first = loadTelegramBridge();
    const failedScript = document.head.querySelector<HTMLScriptElement>('script[data-telegram-web-app]')!;
    failedScript.dispatchEvent(new Event("error"));
    await expect(first).rejects.toThrow("telegram_bridge_load_failed");
    expect(failedScript.isConnected).toBe(false);

    const second = loadTelegramBridge();
    const retryScript = document.head.querySelector<HTMLScriptElement>('script[data-telegram-web-app]')!;
    expect(retryScript).not.toBe(failedScript);
    window.Telegram = { WebApp: {
      initData: "signed",
      ready: vi.fn(),
      expand: vi.fn(),
      close: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
    } };
    retryScript.dispatchEvent(new Event("load"));
    await expect(second).resolves.toBe(window.Telegram.WebApp);
  });

  it("settles a load event without WebApp as outside Telegram and clears the script", async () => {
    const bridge = loadTelegramBridge();
    const script = document.head.querySelector<HTMLScriptElement>('script[data-telegram-web-app]')!;
    script.dispatchEvent(new Event("load"));
    await expect(bridge).resolves.toBeUndefined();
    expect(script.isConnected).toBe(false);
  });
});

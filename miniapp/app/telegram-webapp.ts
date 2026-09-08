const MOBILE_TELEGRAM_PLATFORMS = new Set(["android", "ios"]);

export type TelegramWebApp = {
  initData: string;
  platform?: string;
  version?: string;
  ready: () => void;
  expand: () => void;
  requestFullscreen?: () => void;
  close: () => void;
  setHeaderColor: (color: string) => void;
  setBackgroundColor: (color: string) => void;
  openLink?: (url: string) => void;
  openTelegramLink?: (url: string) => void;
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
  };
};

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

const TELEGRAM_BRIDGE_SELECTOR = "script[data-telegram-web-app]";
const TELEGRAM_BRIDGE_SRC = "https://telegram.org/js/telegram-web-app.js?63";
let bridgeLoad: Promise<TelegramWebApp | undefined> | null = null;

/** Load the Telegram bridge after hydration so it cannot mutate SSR-owned <html> attributes. */
export function loadTelegramBridge(): Promise<TelegramWebApp | undefined> {
  if (typeof window === "undefined") return Promise.resolve(undefined);
  const existing = window.Telegram?.WebApp;
  if (existing) return Promise.resolve(existing);
  if (bridgeLoad) return bridgeLoad;

  bridgeLoad = new Promise<TelegramWebApp | undefined>((resolve, reject) => {
    let script = document.querySelector<HTMLScriptElement>(TELEGRAM_BRIDGE_SELECTOR);
    const finish = () => {
      const webApp = window.Telegram?.WebApp;
      if (!webApp) script?.remove();
      resolve(webApp);
    };
    const fail = () => {
      script?.remove();
      reject(new Error("telegram_bridge_load_failed"));
    };
    if (!script) {
      script = document.createElement("script");
      script.src = TELEGRAM_BRIDGE_SRC;
      script.async = true;
      script.dataset.telegramWebApp = "true";
    }
    script.addEventListener("load", finish, { once: true });
    script.addEventListener("error", fail, { once: true });
    if (!script.isConnected) document.head.appendChild(script);
  }).finally(() => {
    bridgeLoad = null;
  });
  return bridgeLoad;
}

export function shouldRequestFullscreen(
  platform: string | undefined,
  version: string | undefined,
): boolean {
  const majorVersion = Number(version?.split(".", 1)[0]);
  return Boolean(
    platform &&
    MOBILE_TELEGRAM_PLATFORMS.has(platform.toLowerCase()) &&
    Number.isFinite(majorVersion) &&
    majorVersion >= 8,
  );
}

export function initializeTelegram(): TelegramWebApp | undefined {
  const webApp = window.Telegram?.WebApp;
  if (!webApp) return undefined;
  webApp.ready();
  webApp.expand();
  if (shouldRequestFullscreen(webApp.platform, webApp.version)) {
    try {
      webApp.requestFullscreen?.();
    } catch {
      // Expanded mode remains usable in Telegram clients without fullscreen support.
    }
  }
  return webApp;
}

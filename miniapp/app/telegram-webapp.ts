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

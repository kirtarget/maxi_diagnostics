import type { Metadata } from "next";
import type { CSSProperties, ReactNode } from "react";

import brand from "../../school/brand.json";
import "./globals.css";

export const metadata: Metadata = {
  title: `${brand.name} — диагностика знаний`,
  description: `Диагностика знаний от ${brand.name} с сохранением прогресса и результатом в Telegram.`,
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const schoolStyle = {
    "--brand-primary": brand.colors.primary,
    "--brand-accent": brand.colors.accent,
    "--brand-background": brand.colors.background,
  } as CSSProperties;
  return (
    <html lang="ru" style={schoolStyle}>
      <head>
        {/* Telegram requires its bridge before the Mini App initializes. */}
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script src="https://telegram.org/js/telegram-web-app.js?63" />
      </head>
      <body>{children}</body>
    </html>
  );
}

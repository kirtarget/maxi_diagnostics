import type { Metadata, Viewport } from "next";
import type { CSSProperties, ReactNode } from "react";

import brand from "../../school/brand.json";
import "./globals.css";

export const metadata: Metadata = {
  title: `${brand.name} — диагностика знаний`,
  description: `Диагностика знаний от ${brand.name} с сохранением прогресса и результатом в Telegram.`,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  userScalable: true,
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const schoolStyle = {
    "--brand-primary": brand.colors.primary,
    "--brand-accent": brand.colors.accent,
    "--brand-background": brand.colors.background,
  } as CSSProperties;
  return (
    <html lang="ru" style={schoolStyle}>
      <body>{children}</body>
    </html>
  );
}

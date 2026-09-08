# KIR-235 accessibility verification

The in-app dev-browser audit reproduced a React hydration mismatch on `<html>`.
The Telegram bridge was synchronously loaded in SSR `<head>` and added viewport
CSS variables before hydration. The bridge now loads from the client bootstrap
effect, after hydration, so SSR-owned `<html>` attributes stay unchanged while
Telegram behavior is preserved afterward. The post-fix unauthenticated/loading
surface has zero browser warnings or errors. Authenticated home, profile, and
league routes remain unverified because real Telegram `initData` is unavailable.

The accessibility slice is covered by DOM keyboard tests and static CSS token,
focus, sizing, and contrast contracts in `miniapp/app/accessibility.test.tsx`.

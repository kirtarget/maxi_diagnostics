import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NotTelegramScreen } from "./navigation-screens";

describe("not-telegram state", () => {
  it("explains the Telegram-only flow and links to the school bot", () => {
    const html = renderToStaticMarkup(<NotTelegramScreen botUrl="https://t.me/maxi_diagnostics_bot" />);
    expect(html).toContain("Открой в Telegram");
    expect(html).toContain("Перейти в бота");
    expect(html).toContain("https://t.me/maxi_diagnostics_bot");
  });

  it("omits the bot button when no bot username is configured", () => {
    const html = renderToStaticMarkup(<NotTelegramScreen botUrl={null} />);
    expect(html).toContain("Открой в Telegram");
    expect(html).not.toContain("Перейти в бота");
  });
});

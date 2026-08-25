import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LeagueScreen } from "./league-screen";

describe("LeagueScreen", () => {
  it("renders server order and highlights only the server-marked user", () => {
    const html = renderToStaticMarkup(<LeagueScreen state={{ kind: "ready", data: {
      status: "active", week_start: "24 августа", week_end: "30 августа",
      rows: [
        { rank: 3, display_label: "Синий маяк", xp_week: 20, is_me: false },
        { rank: 7, display_label: "Тихий космос", xp_week: 12, is_me: true },
      ], me: { rank: 7, xp_week: 12 },
    } }} />);
    expect(html.indexOf("Синий маяк")).toBeLessThan(html.indexOf("Тихий космос"));
    expect(html).toContain("league-row-me");
    expect(html).toContain("Место 7");
  });

  it("renders loading, error, and forming states", () => {
    expect(renderToStaticMarkup(<LeagueScreen state={{ kind: "loading" }} />)).toContain("Загружаем рейтинг");
    expect(renderToStaticMarkup(<LeagueScreen state={{ kind: "error", message: "Не удалось загрузить рейтинг" }} />)).toContain("Не удалось загрузить рейтинг");
    expect(renderToStaticMarkup(<LeagueScreen state={{ kind: "ready", data: { status: "forming", week_start: "24 августа", week_end: "30 августа", rows: [], me: null } }} />)).toContain("Лига формируется");
  });
});

import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { normalizeOffer, OfferSurface, type OfferTelemetryEvent } from "./offer-ux";

describe("offer UX", () => {
  it("returns no surface for empty configuration", () => {
    expect(normalizeOffer({})).toBeNull();
    expect(normalizeOffer({ id: "x", label: "", button: "Открыть", url: "https://school.example" })).toBeNull();
  });

  it("maps the configured fields without inventing advertiser data", () => {
    expect(normalizeOffer({
      id: "exam-preparation",
      label: "Подготовка",
      button: "Узнать больше",
      url: "https://school.example/promo",
    })).toEqual({
      offerId: "exam-preparation",
      title: "Подготовка",
      cta: "Узнать больше",
      url: "https://school.example/promo",
    });
  });

  it("renders an explicit close control and a configured link", () => {
    const onClose = () => undefined;
    const html = renderToStaticMarkup(
      <OfferSurface
        offer={{ offerId: "offer-1", title: "Курс", cta: "Открыть", url: "https://school.example" }}
        placement="diagnostic_result"
        onClose={onClose}
      />,
    );
    expect(html).toContain('aria-label="Закрыть предложение"');
    expect(html).toContain('href="https://school.example"');
    expect(typeof onClose).toBe("function");
  });

  it("keeps telemetry scoped to the offer and sends one impression per mount", () => {
    const source = readFileSync(new URL("./offer-ux.tsx", import.meta.url), "utf8");
    expect(source).toContain("const impressionSent = useRef(false)");
    expect(source).toContain('action: \"impression\"');
    expect(source).not.toMatch(/initData|answers|results|profile|metadata/iu);
    const event: OfferTelemetryEvent = { event_id: "e", offer_id: "o", placement: "home", action: "impression" };
    expect(Object.keys(event).sort()).toEqual(["action", "event_id", "offer_id", "placement"]);
  });
});

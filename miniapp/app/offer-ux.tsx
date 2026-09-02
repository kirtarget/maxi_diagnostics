"use client";

import { useEffect, useRef } from "react";

export type OfferPlacement = "home" | "diagnostic_result" | "trainer" | "trainer_wrong" | "trainer_no_lives" | "forecast";
export type OfferEventAction = "impression" | "click" | "dismiss";

export type ConfiguredOffer = {
  id?: string;
  label?: string;
  button?: string;
  url?: string;
  image?: string;
  title?: string;
  body?: string;
  cta?: string;
};

export type OfferViewModel = {
  offerId: string;
  title: string;
  body?: string;
  cta: string;
  url: string;
  image?: string;
};

export type OfferTelemetryEvent = {
  event_id: string;
  offer_id: string;
  placement: OfferPlacement;
  action: OfferEventAction;
};

export type OfferDismissalState = Partial<Record<OfferPlacement, boolean>>;

export function dismissOffer(state: OfferDismissalState, placement: OfferPlacement): OfferDismissalState {
  return { ...state, [placement]: true };
}

function eventId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function normalizeOffer(offer: ConfiguredOffer): OfferViewModel | null {
  const offerId = offer.id?.trim();
  const url = offer.url?.trim();
  const title = (offer.title ?? offer.label)?.trim();
  const cta = (offer.cta ?? offer.button)?.trim();
  if (!offerId || !url || !title || !cta) return null;
  return {
    offerId,
    title,
    body: offer.body?.trim() || undefined,
    cta,
    url,
    image: offer.image?.trim() || undefined,
  };
}

export function OfferSurface({
  offer,
  placement,
  onClose,
  onEvent,
}: {
  offer: OfferViewModel;
  placement: OfferPlacement;
  onClose: () => void;
  onEvent?: (event: OfferTelemetryEvent) => void;
}) {
  const impressionSent = useRef(false);
  useEffect(() => {
    if (impressionSent.current) return;
    impressionSent.current = true;
    onEvent?.({ event_id: eventId(), offer_id: offer.offerId, placement, action: "impression" });
  }, [offer.offerId, placement, onEvent]);

  const emit = (action: OfferEventAction) => {
    onEvent?.({ event_id: eventId(), offer_id: offer.offerId, placement, action });
  };

  return (
    <aside className={`offer-surface offer-surface-${placement}`} aria-label="Предложение школы">
      <button className="offer-surface-close" type="button" onClick={() => { emit("dismiss"); onClose(); }} aria-label="Закрыть предложение">
        ×
      </button>
      {offer.image && <img className="offer-surface-image" src={offer.image} alt="" />}
      <div className="offer-surface-copy">
        <span className="offer-surface-label">Предложение школы</span>
        <h2>{offer.title}</h2>
        {offer.body && <p>{offer.body}</p>}
        <a href={offer.url} target="_blank" rel="noreferrer" onClick={() => emit("click")}>
          {offer.cta} <span aria-hidden="true">→</span>
        </a>
      </div>
    </aside>
  );
}

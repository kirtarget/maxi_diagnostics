export type ApiCredential =
  | { init_data: string; card_ticket?: never }
  | { card_ticket: string; init_data?: never };

export type CredentialInput = ApiCredential | string;

export function isCardCredential(value: CredentialInput): value is Extract<ApiCredential, { card_ticket: string }> {
  return typeof value !== "string" && typeof value.card_ticket === "string";
}

const CARD_STORAGE_KEY = "admission-card-ticket";

export function readCardCredential(browser: Window = window): ApiCredential | null {
  const fragment = new URLSearchParams(browser.location.hash.slice(1));
  const hasCard = fragment.has("card");
  let ticket = hasCard ? fragment.get("card") : null;
  try {
    if (!hasCard) ticket = browser.sessionStorage.getItem(CARD_STORAGE_KEY);
    else if (ticket && ticket.length <= 512) browser.sessionStorage.setItem(CARD_STORAGE_KEY, ticket);
    else browser.sessionStorage.removeItem(CARD_STORAGE_KEY);
  } catch {
    // Restricted WebViews can deny storage; the in-memory credential still works.
  }
  if (hasCard) browser.history.replaceState(browser.history.state, "", browser.location.pathname + browser.location.search);
  if (!ticket || ticket.length > 512) return null;
  return { card_ticket: ticket };
}

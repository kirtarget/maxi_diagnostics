// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useBootstrap, type BootstrapSession } from "./use-bootstrap";
import { loadBootstrap } from "./api";
import { initializeTelegram, loadTelegramBridge } from "./telegram-webapp";

vi.mock("./api", () => ({
  loadBootstrap: vi.fn().mockResolvedValue({ session_scope: "card-scope" }),
  recordOfferEvent: vi.fn(),
  startOnboarding: vi.fn(),
}));
vi.mock("./telegram-webapp", () => ({ initializeTelegram: vi.fn(), loadTelegramBridge: vi.fn() }));

afterEach(() => {
  sessionStorage.clear();
  history.replaceState(null, "", "/");
  vi.clearAllMocks();
});

it("bootstraps a card without loading or calling the Telegram SDK", async () => {
  history.replaceState(null, "", "/#card=signed-card-ticket");
  let session: BootstrapSession;
  function Harness() { session = useBootstrap(); return null; }
  const container = document.createElement("div");
  const root = createRoot(container);
  await act(async () => { root.render(<Harness />); });
  try {
    await act(async () => { await session!.actions.load(); });
    expect(loadBootstrap).toHaveBeenCalledWith({ card_ticket: "signed-card-ticket" });
    expect(loadTelegramBridge).not.toHaveBeenCalled();
    expect(initializeTelegram).not.toHaveBeenCalled();
    expect(session!.state.cardMode).toBe(true);
    expect(location.hash).toBe("");
  } finally { await act(async () => { root.unmount(); }); }
});

// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readCardCredential } from "./api-credential";
import { postDiagnostic } from "./api";

beforeEach(() => {
  sessionStorage.clear();
  history.replaceState(null, "", "/");
});

describe("admission card credential", () => {
  it("prefers the fragment, removes it and retains the ticket for reload", () => {
    sessionStorage.setItem("admission-card-ticket", "old");
    history.replaceState(null, "", "/?keep=yes#card=new-ticket");
    expect(readCardCredential()).toEqual({ card_ticket: "new-ticket" });
    expect(location.hash).toBe("");
    expect(location.search).toBe("?keep=yes");
    expect(readCardCredential()).toEqual({ card_ticket: "new-ticket" });
  });

  it("works when session storage is denied", () => {
    history.replaceState(null, "", "/#card=ticket");
    const denied = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    expect(readCardCredential()).toEqual({ card_ticket: "ticket" });
    expect(location.hash).toBe("");
    denied.mockRestore();
  });

  it("rejects empty and oversized fragments and removes stale credentials", () => {
    sessionStorage.setItem("admission-card-ticket", "old");
    history.replaceState(null, "", "/#card=" + "a".repeat(513));
    expect(readCardCredential()).toBeNull();
    expect(readCardCredential()).toBeNull();
    history.replaceState(null, "", "/#card=");
    expect(readCardCredential()).toBeNull();
  });

  it("posts card authentication without Telegram init data", async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    await postDiagnostic("/test", { card_ticket: "ticket" }, { session_scope: "scope" }, fetcher);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ card_ticket: "ticket", session_scope: "scope" });
  });
});

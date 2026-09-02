"use client";

import { useCallback, useRef, useState, type RefObject } from "react";

import { loadBootstrap, loadWeeklyLeague, recordOfferEvent } from "./api";
import type { LeagueScreenState } from "./league-model";
import { dismissOffer, type OfferDismissalState, type OfferPlacement, type OfferTelemetryEvent } from "./offer-ux";
import { initializeTelegram } from "./telegram-webapp";
import type { BootstrapResponse, Screen } from "./types";

export type BootstrapState = {
  bootstrap: BootstrapResponse | null;
  error: string | null;
  outsideTelegram: boolean;
  sessionCompletions: number;
  dismissedOfferPlacements: OfferDismissalState;
  leagueState: LeagueScreenState;
};

/**
 * `apply` commits the loaded payload. The caller runs it only after its own
 * staleness guard passes, so an abandoned load never overwrites fresher state.
 */
export type BootstrapLoad =
  | { status: "outside" }
  | { status: "ready"; data: BootstrapResponse; apply: () => void };

export type BootstrapActions = {
  load(): Promise<BootstrapLoad>;
  setError(message: string | null): void;
  countCompletion(): void;
  dismissOfferPlacement(placement: OfferPlacement): void;
  handleOfferEvent(event: OfferTelemetryEvent): void;
  openLeague(): Promise<void>;
};

export type BootstrapSession = {
  state: BootstrapState;
  actions: BootstrapActions;
  initData: RefObject<string>;
  schoolId: RefObject<string | null>;
  sessionScopeRef: RefObject<string | null>;
  sessionScope: string | undefined;
};

export function useBootstrap(setScreen: (screen: Screen) => void): BootstrapSession {
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outsideTelegram, setOutsideTelegram] = useState(false);
  const [sessionCompletions, setSessionCompletions] = useState(0);
  const [dismissedOfferPlacements, setDismissedOfferPlacements] = useState<OfferDismissalState>({});
  const [leagueState, setLeagueState] = useState<LeagueScreenState>({ kind: "loading" });
  const initData = useRef("");
  const schoolId = useRef<string | null>(null);
  const sessionScopeRef = useRef<string | null>(null);

  const sessionScope = bootstrap?.session_scope;

  const load = useCallback(async (): Promise<BootstrapLoad> => {
    const webApp = initializeTelegram();
    initData.current = webApp?.initData ?? "";
    if (!initData.current) {
      setOutsideTelegram(true);
      return { status: "outside" };
    }
    setOutsideTelegram(false);
    const data = await loadBootstrap(initData.current);
    return {
      status: "ready",
      data,
      apply: () => {
        setBootstrap(data);
        schoolId.current = data.school.brand.school_id;
        sessionScopeRef.current = data.session_scope;
        webApp?.setHeaderColor(data.school.brand.colors.background);
        webApp?.setBackgroundColor(data.school.brand.colors.background);
      },
    };
  }, []);

  const countCompletion = useCallback(() => {
    setSessionCompletions((count) => count + 1);
  }, []);

  const dismissOfferPlacement = useCallback((placement: OfferPlacement) => {
    setDismissedOfferPlacements((current) => dismissOffer(current, placement));
  }, []);

  const handleOfferEvent = useCallback((event: OfferTelemetryEvent) => {
    if (!sessionScope || !initData.current) return;
    void recordOfferEvent(initData.current, {
      session_scope: sessionScope,
      event_id: event.event_id,
      placement: event.placement,
      offer_id: event.offer_id,
      event_type: event.action,
    }).catch(() => undefined);
  }, [sessionScope]);

  const openLeague = useCallback(async () => {
    if (!sessionScope || !initData.current) return;
    setLeagueState({ kind: "loading" });
    setScreen("league");
    try {
      const data = await loadWeeklyLeague(initData.current, sessionScope);
      setLeagueState({ kind: "ready", data });
    } catch {
      setLeagueState({ kind: "error", message: "Не удалось загрузить рейтинг. Повтори попытку." });
    }
  }, [sessionScope, setScreen]);

  return {
    state: {
      bootstrap,
      error,
      outsideTelegram,
      sessionCompletions,
      dismissedOfferPlacements,
      leagueState,
    },
    actions: {
      load,
      setError,
      countCompletion,
      dismissOfferPlacement,
      handleOfferEvent,
      openLeague,
    },
    initData,
    schoolId,
    sessionScopeRef,
    sessionScope,
  };
}

"use client";

import { useCallback, useState } from "react";

import { loadToday, loadTopicPath } from "./api";
import type { TodaySession, TopicPathResponse } from "./types";

/** Today's session for the home screen. `ready` also covers `path_complete` and `no_diagnostic`; the status inside the payload steers the screen. */
export type TodayState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; today: TodaySession }
  | { kind: "error" };

/** The full topic path for the path screen, loaded on demand from `/path`. */
export type PathState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; path: TopicPathResponse }
  | { kind: "error" };

export type TodaySessionHook = {
  today: TodayState;
  path: PathState;
  /** Load or reload today's session. Safe to call repeatedly; the last response wins. */
  refreshToday: () => Promise<TodaySession | null>;
  /** Load the authoritative topic path for the path screen. */
  loadPath: (diagnosticId: string, contentVersion: string) => Promise<void>;
};

export function useTodaySession({
  initData,
  sessionScope,
}: {
  initData: { current: string };
  sessionScope: string | undefined;
}): TodaySessionHook {
  const [today, setToday] = useState<TodayState>({ kind: "idle" });
  const [path, setPath] = useState<PathState>({ kind: "idle" });

  const refreshToday = useCallback(async (): Promise<TodaySession | null> => {
    if (!sessionScope || !initData.current) return null;
    setToday((current) => (current.kind === "ready" ? current : { kind: "loading" }));
    try {
      const response = await loadToday(initData.current, { session_scope: sessionScope });
      setToday({ kind: "ready", today: response });
      return response;
    } catch {
      setToday({ kind: "error" });
      return null;
    }
  }, [initData, sessionScope]);

  const loadPath = useCallback(async (diagnosticId: string, contentVersion: string): Promise<void> => {
    if (!sessionScope || !initData.current) return;
    setPath((current) => (current.kind === "ready" ? current : { kind: "loading" }));
    try {
      const response = await loadTopicPath(initData.current, {
        session_scope: sessionScope,
        diagnostic_id: diagnosticId,
        content_version: contentVersion,
      });
      setPath({ kind: "ready", path: response });
    } catch {
      setPath({ kind: "error" });
    }
  }, [initData, sessionScope]);

  return { today, path, refreshToday, loadPath };
}

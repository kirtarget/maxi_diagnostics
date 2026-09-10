import type { TodaySession, TopicPathNode } from "./types";
import { plural } from "./text-utils";

/** Share of the topic the student has mastered, as a whole percent. */
export function topicMasteryPercent(mastered: number, total: number): number {
  if (total <= 0) return 0;
  return Math.round((Math.min(mastered, total) / total) * 100);
}

/** Caption under a path node, keyed by its status. */
export function topicNodeCaption(node: TopicPathNode): string {
  if (node.status === "done") return `Тема пройдена · ${node.mastered}/${node.total}`;
  if (node.status === "current") return `Сейчас здесь · ${node.mastered}/${node.total}`;
  return "Откроется дальше по пути";
}

/**
 * The home preview shows the path around the student: the last done topic, the
 * current one, and the next locked topic. Falls back to the first nodes when
 * there is no current topic yet.
 */
export function pathPreview(nodes: TopicPathNode[], limit = 3): TopicPathNode[] {
  if (nodes.length <= limit) return nodes;
  const currentIndex = nodes.findIndex((node) => node.status === "current");
  if (currentIndex < 0) return nodes.slice(0, limit);
  const start = Math.max(0, currentIndex - 1);
  return nodes.slice(start, start + limit);
}

/** How the home CTA reads: "Заниматься · N заданий · Тема". */
export function todayCtaSummary(today: TodaySession): { size: string; topic: string | null } {
  const size = `${today.size} ${plural(today.size, ["задание", "задания", "заданий"])}`;
  return { size, topic: today.topic };
}

/** Estimated minutes label for the session, e.g. "~4 мин". */
export function estimatedMinutesLabel(minutes: number): string {
  return `~${Math.max(1, Math.round(minutes))} мин`;
}

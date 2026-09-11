import type { CheckpointNode, CheckpointStatus } from "./types";

/** A short label for the block a checkpoint closes, built from its unit topics. */
export function checkpointBlockLabel(node: CheckpointNode): string {
  const topics = node.topics.filter((topic) => topic.trim().length > 0);
  if (topics.length === 0) return `Блок ${node.unit_index + 1}`;
  if (topics.length <= 2) return topics.join(", ");
  return `${topics[0]} — ${topics[topics.length - 1]}`;
}

/** The day a throttled checkpoint reopens, e.g. "12 сентября". Empty when unknown. */
export function checkpointReopenLabel(availableAt: string | null): string {
  if (!availableAt) return "";
  const when = new Date(availableAt);
  if (Number.isNaN(when.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(when);
}

/** Caption under a checkpoint node, keyed by its status. */
export function checkpointNodeCaption(node: CheckpointNode): string {
  switch (node.status) {
    case "available":
      return `Короткий срез закрывает блок «${checkpointBlockLabel(node)}»`;
    case "cooldown": {
      const reopen = checkpointReopenLabel(node.available_at);
      return reopen ? `Следующий чекпоинт откроется ${reopen}` : "Чекпоинт скоро откроется снова";
    }
    case "passed": {
      const total = node.question_total ?? 0;
      const mastered = node.mastered_count ?? 0;
      return total > 0 ? `Пройден · ${mastered}/${total}` : "Пройден";
    }
    default:
      return "Откроется, когда закроешь темы блока";
  }
}

/** The glyph a checkpoint node shows for its status. */
export function checkpointNodeMarker(status: CheckpointStatus): string {
  if (status === "passed") return "✓";
  if (status === "locked") return "🔒";
  return "◆";
}

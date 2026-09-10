import { plural } from "./text-utils";
import type { Question } from "./types";
import type { TrainerAnswerResponse, TrainerMode } from "./trainer-model";

/** ё and е are the same letter to a grader, and case never decides an option. */
function normalizeLabel(label: string): string {
  return label.replace(/ё/gu, "е").replace(/Ё/gu, "Е").replace(/\s+/gu, " ").trim().toLocaleLowerCase("ru-RU");
}

/**
 * The server sends the correct answer as option labels, not ids, so the screen
 * has to match on labels to colour the right row. No match means no green
 * marker, which is better than promising the wrong one.
 */
export function correctOptionIds(question: Question, correctAnswer: string | null | undefined): string[] {
  if (!correctAnswer) return [];
  if (question.type !== "single" && question.type !== "multiple") return [];
  // A single choice with a stress mark arrives as "label · ударение: …".
  const wanted = new Set(
    correctAnswer.split(/,\s*/u).map((part) => normalizeLabel(part.split(" · ударение:")[0])),
  );
  return question.options.filter((option) => wanted.has(normalizeLabel(option.label))).map((option) => option.id);
}

export type TrainerLifeNote = {
  text: string;
  /** The last life is a warning, not a receipt, so the screen can raise it. */
  isWarning: boolean;
};

/**
 * A life is spent silently on the server. Say so, and say what is left, because
 * the "Жизни закончились" screen must never be the first news of it.
 */
export function lifeNote(
  result: Pick<TrainerAnswerResponse, "life_delta" | "lives_remaining">,
  mode: TrainerMode,
): TrainerLifeNote | null {
  if (mode === "mistakes" || result.life_delta >= 0) return null;
  const left = result.lives_remaining;
  if (left <= 0) return { text: "−1 жизнь · жизни закончились", isWarning: true };
  return {
    text: `−1 жизнь · осталось ${left} ${plural(left, ["жизнь", "жизни", "жизней"])}`,
    isWarning: left === 1,
  };
}

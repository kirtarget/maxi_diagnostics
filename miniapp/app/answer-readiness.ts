import { isValidNumericInput, isValidTextInput } from "./answer-values";
import { matchingModelFromQuestion, matchingReadiness } from "./matching-answer";
import { isCompleteSequenceMatchingAnswer, parseSequenceMatchingPrompt } from "./sequence-matching";
import { isCompleteTableGapAnswer, parseTableGapPrompt } from "./table-gap-matching";
import type { AnswerValue, Question } from "./types";

/** Shared by the diagnostic question screen and the trainer: is the answer complete, and if not, why. */
export type AnswerReadiness = {
  isAnswered: boolean;
  reason: string;
};

export function answerReadiness(question: Question, answer: AnswerValue | undefined, subject?: string): AnswerReadiness {
  switch (question.type) {
    case "single":
      return typeof answer === "string" && answer.length > 0
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: "Выбери вариант" };
    case "multiple": {
      const selected = Array.isArray(answer) ? answer.length : 0;
      return selected === question.selection_limit
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: `Выбрано ${selected} из ${question.selection_limit}` };
    }
    case "matching":
      // The editor owns the markers it draws, so the hint has to ask for those.
      return matchingReadiness(matchingModelFromQuestion(question, subject), answer);
    case "text":
      return isValidTextInput(answer, question.max_length)
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: "Введи ответ" };
    case "input": {
      const tableGap = parseTableGapPrompt(question.prompt, question);
      if (tableGap) {
        if (isCompleteTableGapAnswer(tableGap, answer)) return { isAnswered: true, reason: "" };
        const selected = typeof answer === "string" ? [...answer] : [];
        const duplicate = selected.find((value, index) => selected.indexOf(value) !== index);
        return duplicate
          ? { isAnswered: false, reason: `Вариант ${duplicate} выбран дважды` }
          : {
            isAnswered: false,
            reason: `Осталось заполнить: ${tableGap.markers.slice(selected.length).join(", ")}`,
          };
      }
      const matching = parseSequenceMatchingPrompt(question.prompt, question);
      if (matching) {
        if (isCompleteSequenceMatchingAnswer(matching, answer)) return { isAnswered: true, reason: "" };
        const selected = typeof answer === "string" ? [...answer] : [];
        const duplicate = matching.allowReuse
          ? undefined
          : selected.find((value, index) => selected.indexOf(value) !== index);
        return duplicate
          ? { isAnswered: false, reason: `Вариант ${duplicate} выбран дважды` }
          : {
            isAnswered: false,
            reason: `Заполнено ${Math.min(selected.length, matching.answerLength)} из ${matching.answerLength}`,
          };
      }
      if (question.answer_format === "sequence" && question.answer_length) {
        // The server accepts exactly `answer_length` digits, so the button must
        // not promise a transition the completion request will refuse.
        const digits = typeof answer === "string" ? [...answer] : [];
        const wellFormed = digits.every((value) => /^\d$/u.test(value));
        const duplicate = question.allow_reuse === false
          ? digits.find((value, index) => digits.indexOf(value) !== index)
          : undefined;
        if (wellFormed && !duplicate && digits.length === question.answer_length) {
          return { isAnswered: true, reason: "" };
        }
        return duplicate
          ? { isAnswered: false, reason: `Вариант ${duplicate} выбран дважды` }
          : { isAnswered: false, reason: `Заполнено ${Math.min(digits.length, question.answer_length)} из ${question.answer_length}` };
      }
      return isValidNumericInput(answer)
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: "Введи число" };
    }
    default: {
      const exhaustiveQuestion: never = question;
      return exhaustiveQuestion;
    }
  }
}

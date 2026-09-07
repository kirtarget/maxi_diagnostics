import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { questionProgress, QuestionView } from "./question-screen";
import type { AnswerValue, Brand, Question } from "./types";


const question: Question = {
  id: "q-image",
  type: "input",
  topic: "Биология",
  title: "Задание 6",
  prompt: "Установите соответствие между структурами белка.\nПРИЗНАК\nА) последовательность аминокислот\nОтвет запишите без пробелов.",
  asset: "assets/questions/q9861.png",
};

const sequenceQuestion: Question = {
  ...question,
  id: "q-sequence",
  prompt: [
    "Установите соответствие.",
    "А) Первый пункт",
    "Б) Второй пункт",
    "1) Первый вариант",
    "2) Второй вариант",
  ].join("\n"),
};

const tableGapQuestion: Question = {
  ...question,
  id: "q-table-gap",
  prompt: [
    "Заполните пустые ячейки таблицы.",
    "Колонка 1",
    "Колонка 2",
    "Колонка 3",
    "(А)",
    "Значение",
    "Значение",
    "Значение",
    "(Б)",
    "Значение",
    "Пропущенные элементы:",
    "1) Первый вариант;",
    "2) Второй вариант.",
  ].join("\n"),
};


describe("QuestionView", () => {
  it.each([
    ["single", { ...question, type: "single", options: [{ id: "a", label: "А" }] } as Question, undefined, "a"],
    ["multiple", {
      ...question,
      type: "multiple",
      options: [{ id: "a", label: "А" }, { id: "b", label: "Б" }],
      selection_limit: 2,
    } as Question, ["a"], ["a", "b"]],
    ["matching", {
      ...question,
      type: "matching",
      items: [{ id: "a", label: "А" }, { id: "b", label: "Б" }],
      options: [{ id: "1", label: "Один" }, { id: "2", label: "Два" }],
    } as Question, { a: "1" }, { a: "1", b: "2" }],
    ["input", question, "не число", "12"],
    ["input sequence", sequenceQuestion, "1", "12"],
    ["input table gap", tableGapQuestion, "1", "12"],
    ["text", { ...question, type: "text", max_length: 40 } as Question, "   ", "но"],
  ])("enables the next action only for a complete %s answer", (_type, currentQuestion, incomplete, complete) => {
    const renderQuestion = (answer: AnswerValue | undefined) => renderToStaticMarkup(
      <QuestionView
        question={currentQuestion}
        index={0}
        total={3}
        answer={answer}
        labels={{
          back: "Назад",
          task_label: "Задание",
          of_label: "из",
          illustration_alt: "Иллюстрация к заданию",
          next_question: "Следующее задание",
          get_result: "Получить результат",
          answer_label: "Ваш ответ",
          enter_answer: "Введите ответ",
          choose_option: "Выберите вариант",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );

    expect(renderQuestion(incomplete)).toMatch(/class="primary-button question-next" disabled=""/);
    expect(renderQuestion(complete)).not.toMatch(/class="primary-button question-next" disabled=""/);
  });

  it("accepts either a word or digits as a valid text answer", () => {
    const textQuestion = { ...question, type: "text", max_length: 40 } as Question;
    const renderAnswer = (answer: string) => renderToStaticMarkup(
      <QuestionView
        question={textQuestion}
        index={0}
        total={3}
        answer={answer}
        labels={{
          back: "Назад",
          task_label: "Задание",
          of_label: "из",
          illustration_alt: "Иллюстрация к заданию",
          next_question: "Следующее задание",
          get_result: "Получить результат",
          answer_label: "Ваш ответ",
          enter_answer: "Введите ответ",
          choose_option: "Выберите вариант",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );

    expect(renderAnswer("но")).not.toContain('disabled=""');
    expect(renderAnswer("12")).not.toContain('disabled=""');
    expect(renderAnswer("")).toContain('disabled=""');
    expect(renderAnswer("   ")).toContain('disabled=""');
  });

  it("builds game-like progress from the server-owned question position", () => {
    expect(questionProgress(1, 4)).toEqual({
      current: 2,
      total: 4,
      percent: 50,
      message: "Набираем темп",
    });

    const html = renderToStaticMarkup(
      <QuestionView
        question={question}
        index={1}
        total={4}
        answer={undefined}
        labels={{
          back: "Назад",
          task_label: "Задание",
          of_label: "из",
          illustration_alt: "Иллюстрация к заданию",
          next: "Следующее задание",
          answer_label: "Ваш ответ",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );

    expect(html).toContain('role="progressbar"');
    expect(html).toContain('aria-valuenow="50"');
    expect(html).toContain('aria-valuetext="Задание 2 из 4. Набираем темп"');
    expect(html.match(/class="question-progress-node(?: |\")/g)).toHaveLength(4);
    expect(html).toContain("question-progress-node is-current");
    expect(html).toContain("Набираем темп");
  });

  it("shows the subject-and-answer-type chip from the mock", () => {
    const html = renderToStaticMarkup(
      <QuestionView
        question={question}
        subject="Химия"
        index={0}
        total={3}
        answer={undefined}
        labels={{
          back: "Назад",
          task_label: "Задание",
          of_label: "из",
          illustration_alt: "Иллюстрация к заданию",
          answer_label: "Ваш ответ",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );

    expect(html).toContain("question-type-chip");
    expect(html).toContain("Химия · короткий ответ");
  });

  it("labels the collected answer the way the mock does", () => {
    const sequenceQuestion: Question = {
      id: "q-seq",
      type: "input",
      topic: "История",
      title: "Задание 7",
      prompt: [
        "Соотнеси событие и год.",
        "СОБЫТИЕ",
        "А) Куликовская битва",
        "Б) Крещение Руси",
        "1) 1380",
        "2) 988",
        "Ответ запишите в виде последовательности цифр.",
      ].join("\n"),
    };
    const html = renderToStaticMarkup(
      <QuestionView
        question={sequenceQuestion}
        index={0}
        total={3}
        answer="1"
        labels={{
          back: "Назад",
          task_label: "Задание",
          of_label: "из",
          illustration_alt: "Иллюстрация к заданию",
          answer_label: "Ваш ответ",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );

    expect(html).toContain("Твой ответ");
    expect(html).not.toContain("Получившийся ответ");
  });

  it("places an illustration directly after the task stem", () => {
    const html = renderToStaticMarkup(
      <QuestionView
        question={question}
        index={0}
        total={3}
        answer={undefined}
        labels={{
          back: "Назад",
          task_label: "Задание",
          of_label: "из",
          illustration_alt: "Иллюстрация к заданию",
          next: "Следующее задание",
          answer_label: "Ваш ответ",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );

    expect(html.indexOf('src="/assets/questions/q9861.png"')).toBeLessThan(html.indexOf("ПРИЗНАК"));
  });
});

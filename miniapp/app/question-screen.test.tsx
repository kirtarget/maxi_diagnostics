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
    ["single", { ...question, type: "single", options: [{ id: "a", label: "А" }] } as Question, undefined, "a", "Выбери вариант"],
    ["multiple", {
      ...question,
      type: "multiple",
      options: [{ id: "a", label: "А" }, { id: "b", label: "Б" }],
      selection_limit: 2,
    } as Question, ["a"], ["a", "b"], "Выбрано 1 из 2"],
    ["matching", {
      ...question,
      type: "matching",
      items: [{ id: "a", label: "А" }, { id: "b", label: "Б" }],
      options: [{ id: "1", label: "Один" }, { id: "2", label: "Два" }],
    } as Question, { a: "1" }, { a: "1", b: "2" }, "Осталось заполнить: Б"],
    ["input", question, "не число", "12", "Введи число"],
    ["input sequence", sequenceQuestion, "1", "12", "Заполнено 1 из 2"],
    ["input sequence by metadata", {
      ...question,
      prompt: "Расставьте знаки препинания: укажите цифры, на месте которых должны стоять запятые.",
      answer_format: "sequence",
      answer_length: 3,
      allow_reuse: false,
      markers: ["1", "2", "3"],
    } as Question, "12", "134", "Заполнено 2 из 3"],
    ["input table gap", tableGapQuestion, "1", "12", "Осталось заполнить: Б"],
    ["text", { ...question, type: "text", max_length: 40 } as Question, "   ", "но", "Введи ответ"],
  ])("enables the next action only for a complete %s answer", (_type, currentQuestion, incomplete, complete, reason) => {
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

    const incompleteHtml = renderQuestion(incomplete);
    const completeHtml = renderQuestion(complete);

    expect(incompleteHtml).toMatch(/class="primary-button question-next" disabled=""/);
    expect(incompleteHtml).toContain('role="status"');
    expect(incompleteHtml).toContain(reason);
    expect(completeHtml).not.toMatch(/class="primary-button question-next" disabled=""/);
    expect(completeHtml).not.toContain('class="question-next-status"');
  });

  it("keeps the next action in a dedicated sticky bar", () => {
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

    expect(html).toContain('class="question-action-bar"');
    expect(html).toContain('class="question-save-state"');
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

  it("offers an explicit skip action and explains a restored skip marker", () => {
    const available = renderToStaticMarkup(
      <QuestionView
        question={question}
        index={0}
        total={3}
        answer={undefined}
        skipped={false}
        labels={{
          back: "Назад", task_label: "Задание", of_label: "из",
          illustration_alt: "Иллюстрация", next_question: "Следующее задание",
          get_result: "Получить результат", answer_label: "Ваш ответ",
          enter_answer: "Введите ответ", choose_option: "Выберите вариант",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
        onSkip={() => undefined}
      />,
    );
    const skipped = renderToStaticMarkup(
      <QuestionView
        question={question}
        index={0}
        total={3}
        answer="черновик"
        skipped
        labels={{
          back: "Назад", task_label: "Задание", of_label: "из",
          illustration_alt: "Иллюстрация", next_question: "Следующее задание",
          get_result: "Получить результат", answer_label: "Ваш ответ",
          enter_answer: "Введите ответ", choose_option: "Выберите вариант",
        } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
        onSkip={() => undefined}
      />,
    );

    expect(available).toContain('class="question-skip"');
    expect(available).toContain("Не знаю, дальше");
    expect(skipped).not.toContain('class="question-skip"');
    expect(skipped).toContain("Задание пропущено. Можно вернуться и ответить позже.");
    expect(skipped).not.toMatch(/class="primary-button question-next" disabled=""/);
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
        skippedIndexes={[0]}
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
    expect(html).toContain("question-progress-node is-complete is-skipped");
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

  it("renders the real OGE chemistry q04 formula in a matching answer", () => {
    const html = renderToStaticMarkup(
      <QuestionView
        question={{
          id: "sp-chemistry-oge-2022-q4",
          type: "matching",
          topic: "Задание 4",
          title: "Задание 4",
          prompt: "Установите соответствие между формулой соединения и степенью окисления йода в этом соединении.",
          items: [{ id: "i1", label: "А) H_(5)IO_(6)" }],
          options: [{ id: "o1", label: "1) +7" }],
        }}
        subject="Химия"
        index={0}
        total={1}
        answer={{}}
        labels={{ answer_label: "Ваш ответ", choose_option: "Выберите вариант" } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );
    expect(html).toContain("<sub>5</sub>");
    expect(html).toContain("<sub>6</sub>");
  });

  it("keeps Russian q22 text free of math badges", () => {
    const html = renderToStaticMarkup(
      <QuestionView
        question={{ ...question, type: "multiple", prompt: "(1) Текст с числами. Какие высказывания верны?", options: [{ id: "a", label: "1) Ответ" }], selection_limit: 1 }}
        subject="Русский язык"
        index={0}
        total={1}
        answer={[]}
        labels={{ answer_label: "Ваш ответ" } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );
    expect(html).not.toContain("math-expression");
  });

  it("places the real physics q11 instruction directly above the answer field", () => {
    const html = renderToStaticMarkup(
      <QuestionView
        question={{ ...question, type: "input", prompt: "Как изменится величина?\nВ ответ запишите последовательность цифр, соответствующую графам таблицы.\nВведите последовательность цифр без пробелов." }}
        subject="Физика"
        index={0}
        total={1}
        answer=""
        labels={{ answer_label: "Ваш ответ", enter_answer: "Введите ответ" } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );
    const instructionIndex = html.indexOf("question-instruction");
    const answerIndex = html.indexOf('class="short-answer"');
    expect(instructionIndex).toBeGreaterThan(-1);
    expect(instructionIndex).toBeLessThan(answerIndex);
  });

  it("keeps the real Russian EGE q14 instruction and word guidance in one hint", () => {
    const html = renderToStaticMarkup(
      <QuestionView
        question={{
          id: "sp-russian-language-ege-2022-q14",
          type: "text",
          topic: "Задание 14",
          title: "Задание 14",
          prompt: "Определите предложение, в котором оба выделенных слова пишутся СЛИТНО. Раскройте скобки и выпишите эти два слова.\n1) Бабушка уже (ДАВНЫМ)ДАВНО привыкла вставать рано.",
          answer_format: "words",
          lang: "ru",
          max_length: 80,
        }}
        subject="Русский язык"
        index={0}
        total={1}
        answer=""
        labels={{ answer_label: "Ваш ответ", enter_answer: "Введите ответ" } as unknown as Brand["interface"]}
        onAnswer={() => undefined}
        onBack={() => undefined}
        onNext={() => undefined}
      />,
    );
    expect((html.match(/class="question-instruction"/g) ?? []).length).toBe(1);
    expect(html).toContain("выпишите эти два слова");
    expect(html).toContain("Введи два слова");
    expect(html).toContain("Регистр не важен");
    expect(html).toContain("ё = е");
    expect(html).not.toContain("Введите только ответ");
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

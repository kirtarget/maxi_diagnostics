import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { QuestionView } from "./question-screen";
import type { Brand, Question } from "./types";


const question: Question = {
  id: "q-image",
  type: "input",
  topic: "Биология",
  title: "Задание 6",
  prompt: "Установите соответствие между структурами белка.\nПРИЗНАК\nА) последовательность аминокислот\nОтвет запишите без пробелов.",
  asset: "assets/questions/q9861.png",
};


describe("QuestionView", () => {
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

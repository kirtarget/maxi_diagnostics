import { describe, expect, it } from "vitest";

import { isCompleteTableGapAnswer, parseTableGapPrompt } from "./table-gap-matching";

const PROMPT = `Заполните пустые ячейки таблицы, используя список элементов.
Географический объект
Событие (явление, процесс)
Время, когда произошло событие (явление, процесс)
(А)
(Б)
1920-е
Самара
(В)
1910-е
(Г)
Хлебный бунт
(Д)
Новочеркасск
Расстрел демонстрации рабочих
(Е)
Пропущенные элементы:
1) Перекоп;
2) 1650-е;
3) 1710-е;
4) Создание Уфимской директории;
5) Омск;
6) Противостояние Фрунзе и Врангеля;
7) Псков;
8) 1960-е;
9) Создание КОМУЧа.
Введите последовательность цифр без пробелов.`;

describe("parseTableGapPrompt", () => {
  it("restores a three-column table and its missing-cell options", () => {
    const parsed = parseTableGapPrompt(PROMPT);

    expect(parsed?.headers).toEqual([
      "Географический объект",
      "Событие (явление, процесс)",
      "Время, когда произошло событие (явление, процесс)",
    ]);
    expect(parsed?.rows).toHaveLength(4);
    expect(parsed?.rows[0].map((cell) => cell.marker ?? cell.text)).toEqual(["А", "Б", "1920-е"]);
    expect(parsed?.rows[3].map((cell) => cell.marker ?? cell.text)).toEqual([
      "Новочеркасск",
      "Расстрел демонстрации рабочих",
      "Е",
    ]);
    expect(parsed?.options).toHaveLength(9);
  });

  it("requires one valid option for every letter", () => {
    const parsed = parseTableGapPrompt(PROMPT)!;

    expect(isCompleteTableGapAnswer(parsed, "169728")).toBe(true);
    expect(isCompleteTableGapAnswer(parsed, "16972")).toBe(false);
  });
});

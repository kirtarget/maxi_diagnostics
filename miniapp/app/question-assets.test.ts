import { describe, expect, it } from "vitest";

import { questionAssetPaths } from "./question-assets";
import type { Question } from "./types";


function question(overrides: Partial<Question>): Question {
  return {
    id: "q1",
    type: "single",
    topic: "Topic",
    title: "Question",
    prompt: "Prompt",
    options: [{ id: "1", label: "One" }],
    ...overrides,
  } as Question;
}


describe("questionAssetPaths", () => {
  it("keeps backward compatibility with one asset", () => {
    expect(questionAssetPaths(question({ asset: "assets/questions/q1.png" }))).toEqual([
      "/assets/questions/q1.png",
    ]);
  });

  it("returns every safe image path in source order", () => {
    expect(
      questionAssetPaths(
        question({
          assets: [
            "assets/questions/q1-1.png",
            "assets/questions/q1-2.png",
            "../private.png",
          ],
        }),
      ),
    ).toEqual([
      "/assets/questions/q1-1.png",
      "/assets/questions/q1-2.png",
    ]);
  });
});

import { describe, expect, it } from "vitest";

import { plural } from "./text-utils";

describe("Russian plural helper", () => {
  it.each([
    [1, "задание"],
    [2, "задания"],
    [5, "заданий"],
    [11, "заданий"],
    [21, "задание"],
    [-21, "задание"],
  ])("selects the correct form for %s", (count, expected) => {
    expect(plural(count, ["задание", "задания", "заданий"])).toBe(expected);
  });
});

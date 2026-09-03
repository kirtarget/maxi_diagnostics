// The Mini App speaks to the student in one voice: informal "ty", never the
// formal "vy". This mirrors the guard in the backend
// (tests/test_message_tone.py / diagnostic.message_validation) so the two
// surfaces cannot drift back apart.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

const FORMAL_ADDRESS_VERBS = [
  "откройте",
  "выберите",
  "пройдите",
  "нажмите",
  "продолжите",
  "посмотрите",
  "проверьте",
  "попробуйте",
];
const FORMAL_ADDRESS_PATTERN = new RegExp(
  `\\b(?:вы|вас|вам|вами|ваш\\w*|${FORMAL_ADDRESS_VERBS.join("|")})\\b`,
  "iu",
);
const CYRILLIC_STRING_LITERAL = /(["'`])((?:(?!\1).)*[а-яА-ЯёЁ](?:(?!\1).)*)\1/gu;

const appDir = join(__dirname);
const sourceFiles = readdirSync(appDir).filter(
  (name) => (name.endsWith(".ts") || name.endsWith(".tsx")) && !name.endsWith(".test.ts") && !name.endsWith(".test.tsx"),
);

describe("bot/miniapp tone parity: informal address only", () => {
  for (const name of sourceFiles) {
    test(`${name} has no formal-address markers`, () => {
      const source = readFileSync(join(appDir, name), "utf-8");
      const offenders: string[] = [];
      for (const match of source.matchAll(CYRILLIC_STRING_LITERAL)) {
        const literal = match[2];
        if (FORMAL_ADDRESS_PATTERN.test(literal)) {
          offenders.push(literal);
        }
      }
      expect(offenders).toEqual([]);
    });
  }
});

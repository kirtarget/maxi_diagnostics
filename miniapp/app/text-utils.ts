export type PluralForms = readonly [one: string, few: string, many: string];

export function plural(count: number, forms: PluralForms): string {
  const absolute = Math.abs(Math.trunc(count));
  const lastHundred = absolute % 100;
  if (lastHundred >= 11 && lastHundred <= 14) return forms[2];
  const last = absolute % 10;
  if (last === 1) return forms[0];
  if (last >= 2 && last <= 4) return forms[1];
  return forms[2];
}

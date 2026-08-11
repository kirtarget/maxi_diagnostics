import assert from "node:assert/strict";
import { access, readdir, readFile } from "node:fs/promises";
import test from "node:test";

async function productionOutput() {
  const roots = [
    new URL("../.next/server/", import.meta.url),
    new URL("../.next/static/", import.meta.url),
  ];
  const contents = [];

  async function collect(directory) {
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch (error) {
      if (error?.code === "ENOENT") return;
      throw error;
    }
    for (const entry of entries) {
      const target = new URL(entry.name + (entry.isDirectory() ? "/" : ""), directory);
      if (entry.isDirectory()) await collect(target);
      else if (/\.(?:html|js|json|rsc|txt)$/.test(entry.name)) contents.push(await readFile(target, "utf8"));
    }
  }

  for (const directory of roots) await collect(directory);
  return contents.join("\n");
}

test("renders the configured school identity", async () => {
  const output = await productionOutput();
  const brand = JSON.parse(
    await readFile(new URL("../../school/brand.json", import.meta.url), "utf8"),
  );
  assert.equal(typeof brand.name, "string");
  assert.ok(output.includes(brand.name));
  assert.ok(output.includes(`src="/${brand.logo}"`));
  assert.ok(output.includes(`--brand-primary:${brand.colors.primary}`));
  assert.ok(output.includes(`--brand-background:${brand.colors.background}`));
  assert.match(output, /Загружаем диагностику/);
  assert.match(output, /Сканируем знания/);
  assert.match(output, /Прогноз баллов/);
  assert.match(output, /Персональный маршрут/);
});

test("production output contains no answer or private-link leaks", async () => {
  const output = await productionOutput();
  assert.doesNotMatch(output, /https:\/\/docs\.google\.com\/document\/d\//i);
  assert.doesNotMatch(output, /["']correct["']\s*:/i);
});

test("forbidden client-owned data modules are absent", async () => {
  await assert.rejects(access(new URL("../app/diagnostics-catalog.ts", import.meta.url)));
  await assert.rejects(access(new URL("../app/links.ts", import.meta.url)));
});

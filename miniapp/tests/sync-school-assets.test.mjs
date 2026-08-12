import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { syncSchoolAssets } from "../scripts/sync-school-assets.mjs";


test("makes the public asset tree match the school asset tree", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "diagnostic-assets-"));
  context.after(() => rm(root, { recursive: true, force: true }));

  const source = path.join(root, "school", "assets");
  const destination = path.join(root, "miniapp", "public", "assets");
  await mkdir(path.join(source, "questions"), { recursive: true });
  await mkdir(destination, { recursive: true });
  await writeFile(path.join(source, "questions", "q9861.png"), "current-image");
  await writeFile(path.join(destination, "stale-school-logo.png"), "stale-image");

  await syncSchoolAssets(source, destination);

  assert.equal(
    await readFile(path.join(destination, "questions", "q9861.png"), "utf8"),
    "current-image",
  );
  await assert.rejects(
    readFile(path.join(destination, "stale-school-logo.png")),
    { code: "ENOENT" },
  );
});

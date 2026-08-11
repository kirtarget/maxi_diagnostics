import { mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const projectRoot = process.cwd();
const outputPath = path.resolve(
  projectRoot,
  process.argv[2] ?? "THIRD_PARTY_NODE_LICENSES.txt",
);
const lock = JSON.parse(await readFile(path.join(projectRoot, "package-lock.json"), "utf8"));
const licensePattern = /^(licen[cs]e|copying|notice)(\..+)?$/i;

async function regularFile(candidate) {
  try {
    return (await stat(candidate)).isFile();
  } catch {
    return false;
  }
}

async function walkNotices(directory) {
  const notices = [];
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const candidate = path.join(directory, item.name);
    if (item.isDirectory()) notices.push(...await walkNotices(candidate));
    else if (item.isFile() && licensePattern.test(item.name)) notices.push(candidate);
  }
  return notices;
}

async function findLicenses(packageDirectory, relativePackage) {
  const files = await readdir(packageDirectory);
  const direct = files
    .filter((name) => licensePattern.test(name))
    .sort((left, right) => left.localeCompare(right))
    .map((name) => path.join(packageDirectory, name));
  if (relativePackage === "node_modules/next") {
    direct.push(...await walkNotices(path.join(packageDirectory, "dist", "compiled")));
  }
  if (direct.length > 0) return direct;

  if (relativePackage.startsWith("node_modules/@next/")) {
    return [path.join(projectRoot, "node_modules", "next", "license.md")];
  }
  if (relativePackage === "node_modules/client-only") {
    return [path.join(projectRoot, "node_modules", "react", "LICENSE")];
  }
  if (relativePackage.startsWith("node_modules/@img/sharp-libvips-")) {
    const readme = path.join(packageDirectory, "README.md");
    if (await regularFile(readme)) return [readme];
  }
  throw new Error(`license_file_missing:${relativePackage}`);
}

const entries = [];
for (const [relativePackage, metadata] of Object.entries(lock.packages ?? {})) {
  if (!relativePackage.startsWith("node_modules/") || metadata.dev === true) continue;
  const packageDirectory = path.join(projectRoot, relativePackage);
  if (!(await regularFile(path.join(packageDirectory, "package.json")))) continue;

  const packageMetadata = JSON.parse(
    await readFile(path.join(packageDirectory, "package.json"), "utf8"),
  );
  const licenseFiles = await findLicenses(packageDirectory, relativePackage);
  for (const licenseFile of licenseFiles) {
    if (!(await regularFile(licenseFile))) {
      throw new Error(`license_file_missing:${relativePackage}`);
    }
  }
  entries.push({
    name: packageMetadata.name ?? relativePackage.slice("node_modules/".length),
    version: packageMetadata.version ?? metadata.version ?? "bundled",
    declared: packageMetadata.license ?? metadata.license ?? "see included notice",
    notices: await Promise.all(licenseFiles.map(async (licenseFile) => ({
      relative: path.relative(packageDirectory, licenseFile).replaceAll("\\", "/"),
      text: (await readFile(licenseFile, "utf8")).trim(),
    }))),
  });
}

entries.sort((left, right) => `${left.name}@${left.version}`.localeCompare(`${right.name}@${right.version}`));
if (entries.length === 0) throw new Error("license_inventory_empty");

const sections = [
  "Production Node.js dependency licenses",
  "Generated from package-lock.json and the installed production dependency graph.",
  "",
  ...entries.flatMap((entry) => [
    "=".repeat(78),
    `${entry.name}@${entry.version} — ${entry.declared}`,
    "-".repeat(78),
    ...entry.notices.flatMap((notice) => [
      `[${notice.relative}]`,
      notice.text,
      "",
    ]),
    "",
  ]),
];
await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${sections.join("\n")}\n`, "utf8");
console.log(`licenses=${entries.length}`);

import { cp, mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";


export async function syncSchoolAssets(sourceDirectory, destinationDirectory) {
  const destinationParent = path.dirname(destinationDirectory);
  const stagingDirectory = path.join(
    destinationParent,
    `.assets-sync-${process.pid}-${Date.now()}`,
  );

  await mkdir(destinationParent, { recursive: true });
  await rm(stagingDirectory, { recursive: true, force: true });

  try {
    await cp(sourceDirectory, stagingDirectory, { recursive: true });
    await rm(destinationDirectory, { recursive: true, force: true });
    await rename(stagingDirectory, destinationDirectory);
  } catch (error) {
    await rm(stagingDirectory, { recursive: true, force: true });
    throw error;
  }
}


const scriptPath = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  const miniappRoot = path.resolve(path.dirname(scriptPath), "..");
  const repositoryRoot = path.resolve(miniappRoot, "..");
  const sourceDirectory = path.join(repositoryRoot, "school", "assets");
  const destinationDirectory = path.join(miniappRoot, "public", "assets");

  await syncSchoolAssets(sourceDirectory, destinationDirectory);
  console.log(`Synced school assets to ${destinationDirectory}`);
}

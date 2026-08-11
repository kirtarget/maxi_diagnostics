import type { Question } from "./types";


export function safeAssetPath(asset: string): string | undefined {
  if (!/^[A-Za-z0-9_./-]+$/.test(asset) || asset.includes("..")) return undefined;
  return `/${asset.replace(/^\/+/, "")}`;
}


export function questionAssetPaths(question: Question): string[] {
  const assets = question.assets?.length
    ? question.assets
    : question.asset
      ? [question.asset]
      : [];
  return assets.flatMap((asset) => {
    const safe = safeAssetPath(asset);
    return safe ? [safe] : [];
  });
}

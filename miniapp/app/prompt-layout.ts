import type { PromptBlock } from "./question-prompt";

export type PromptLayoutModel = {
  stem: string | null;
  stemRepeat: string | null;
  referenceBlocks: PromptBlock[];
  isLongReference: boolean;
  sentenceAnchors: string[];
};

function blockText(block: PromptBlock): string {
  if (block.kind === "item") return `${block.marker}) ${block.text}`;
  if (block.kind === "table") return [...block.headerRows, ...block.rows].flat().join(" ");
  return block.text;
}

export function promptLayout(blocks: PromptBlock[]): PromptLayoutModel {
  const stem = blocks.find((block) => block.kind === "stem");
  const referenceBlocks = blocks.filter((block) => block.kind !== "stem" && block.kind !== "instruction");
  const referenceText = referenceBlocks.map(blockText).join(" ");
  const sentenceAnchors = [...referenceText.matchAll(/\((\d{1,3})\)/gu)].map((match) => match[1])
    .filter((value, index, values) => values.indexOf(value) === index);
  const stemText = stem?.kind === "stem" ? stem.text : null;
  return {
    stem: stemText,
    // Restating the question above the answer field only earns its place when a
    // reading wall has pushed the heading off screen. A table or an option list
    // keeps the heading in view, so the repeat is pure noise there.
    stemRepeat: stemText && referenceText.length >= 2000 ? stemText : null,
    referenceBlocks,
    isLongReference: referenceText.length >= 600 || referenceBlocks.length >= 8,
    sentenceAnchors,
  };
}

export type PromptAnchorAllocator = {
  blockId(block: PromptBlock): string | undefined;
  sentenceSegments(text: string): Array<{ text: string; anchorId?: string }>;
};

export function createPromptAnchorAllocator(): PromptAnchorAllocator {
  const occurrences = new Map<string, number>();
  const allocate = (marker: string): string => {
    const base = `prompt-sentence-${marker}`;
    const occurrence = (occurrences.get(base) ?? 0) + 1;
    occurrences.set(base, occurrence);
    return occurrence === 1 ? base : `${base}-${occurrence}`;
  };
  return {
    blockId(block) {
      const match = blockText(block).match(/\((\d{1,3})\)/u);
      return match ? allocate(match[1]) : undefined;
    },
    sentenceSegments(text) {
      return text.split(/(?=\(\d{1,3}\))/u).filter(Boolean).map((segment) => {
        const marker = /^\((\d{1,3})\)/u.exec(segment);
        const anchorId = marker ? allocate(marker[1]) : undefined;
        return { text: segment, ...(anchorId ? { anchorId } : {}) };
      });
    },
  };
}

export function focusPromptReference(id: string): void {
  const reference = document.getElementById(id);
  if (!reference) return;
  reference.scrollTop = 0;
  reference.focus({ preventScroll: true });
  reference.scrollIntoView?.({ behavior: "smooth", block: "start" });
}

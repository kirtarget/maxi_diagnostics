"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { textAnswerGuidance } from "./answer-editor";
import { ImageViewer } from "./image-viewer";
import { FormattedMathText, FormattedStem } from "./math-display";
import { createPromptAnchorAllocator, promptLayout, type PromptLayoutModel } from "./prompt-layout";
import { PromptTable } from "./prompt-table";
import { questionAssetPaths } from "./question-assets";
import { parseQuestionPrompt, questionTitleClassName } from "./question-prompt";
import { parseSequenceMatchingPrompt, type SequenceMatchingPrompt } from "./sequence-matching";
import { parseTableGapPrompt } from "./table-gap-matching";
import type { Question } from "./types";

/** Everything the question condition needs, read once so the screen and its header agree. */
export type QuestionBodyModel = {
  layout: PromptLayoutModel;
  /** Instruction blocks, already merged with the short-answer guidance when there is one. */
  instructions: string[];
  imagePaths: string[];
  /** Editors that redraw the reference themselves, so the body must not print it twice. */
  ownsReference: boolean;
  /** The sequence editor that redraws the left column, or null when nothing redraws it. */
  sequence: SequenceMatchingPrompt | null;
};

/**
 * @param withEditor false on read-only surfaces such as the review, where no editor
 * redraws the reference and hiding those blocks would drop the condition.
 */
export function questionBodyModel(question: Question, withEditor = true): QuestionBodyModel {
  const blocks = parseQuestionPrompt(question.prompt);
  const layout = promptLayout(blocks);
  const instructions = blocks.flatMap((block) => block.kind === "instruction" ? [block.text] : []);
  const guidance = question.type === "text" ? textAnswerGuidance(question) : null;
  return {
    layout,
    instructions: guidance && instructions.length > 0 ? [`${instructions.join(" ")} ${guidance}`] : instructions,
    imagePaths: questionAssetPaths(question),
    ownsReference: withEditor && question.type === "input" && Boolean(parseTableGapPrompt(question.prompt, question)),
    sequence: withEditor && question.type === "input"
      ? parseSequenceMatchingPrompt(question.prompt, question)
      : null,
  };
}

export type QuestionBodyProps = {
  question: Question;
  subject?: string;
  model: QuestionBodyModel;
  /** "question" on the diagnostic, "trainer" in the trainer: heading and reference ids. */
  idPrefix: string;
  illustrationAlt: string;
  meta?: ReactNode;
};

/**
 * The condition of a question: chip row, stem, media, reference blocks and instructions.
 * Shared so the trainer cannot drift back into its own flattened layout.
 */
export function QuestionBody({ question, subject, model, idPrefix, illustrationAlt, meta }: QuestionBodyProps) {
  const { layout, instructions, imagePaths } = model;
  const anchors = createPromptAnchorAllocator();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [referenceExpanded, setReferenceExpanded] = useState(false);
  useEffect(() => {
    setReferenceExpanded(false);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    headingRef.current?.focus({ preventScroll: true });
  }, [question.id]);
  const sequenceMatching = model.sequence;
  const referenceId = `${idPrefix}-reference`;

  return (
    <>
      {meta}
      <div className="question-copy">
        <h1
          ref={headingRef}
          tabIndex={-1}
          id={`${idPrefix}-title`}
          className={layout.stem ? questionTitleClassName(layout.stem) : "question-title"}
        >
          <FormattedStem text={layout.stem ?? "Задание"} subject={subject} />
        </h1>
        {imagePaths.length > 0 && (
          <ImageViewer
            className="question-media"
            assets={imagePaths.map((path) => ({ path, alt: question.asset_alt }))}
            fallbackAlt={illustrationAlt}
          />
        )}
        {layout.isLongReference && (
          <button
            className="prompt-reference-toggle"
            type="button"
            aria-controls={referenceId}
            aria-expanded={referenceExpanded}
            onClick={() => setReferenceExpanded((expanded) => !expanded)}
          >
            {referenceExpanded ? "Свернуть текст" : "Развернуть текст"}
          </button>
        )}
        <div
          id={referenceId}
          tabIndex={-1}
          className={`prompt-reference${layout.isLongReference ? " prompt-reference-long" : ""}${referenceExpanded ? " is-expanded" : ""}`}
        >
          {layout.referenceBlocks.map((block, blockIndex) => {
            if (model.ownsReference) return null;
            if (sequenceMatching && (block.kind === "item" || block.kind === "heading" || block.kind === "table")) {
              return null;
            }
            if (
              sequenceMatching
              && block.kind === "paragraph"
              && sequenceMatching.left.some((item) => item.marker === block.text)
            ) return null;
            if (block.kind === "heading") {
              return (
                <h2 id={anchors.blockId(block)} className="question-section-title" key={blockIndex}>
                  <FormattedMathText text={block.text} subject={subject} />
                </h2>
              );
            }
            if (block.kind === "item") {
              return (
                <div className="question-list-item" id={anchors.blockId(block)} key={blockIndex}>
                  <span>{block.marker}</span>
                  <p><FormattedMathText text={block.text} subject={subject} /></p>
                </div>
              );
            }
            if (block.kind === "table") {
              return (
                <div id={anchors.blockId(block)} key={blockIndex}>
                  <PromptTable headerRows={block.headerRows} rows={block.rows} columns={block.columns} subject={subject} />
                </div>
              );
            }
            return (
              <p className="question-paragraph" key={blockIndex}>
                {anchors.sentenceSegments(block.text).map((segment, segmentIndex) => (
                  <span id={segment.anchorId} key={segmentIndex}>
                    <FormattedMathText text={segment.text} subject={subject} />
                  </span>
                ))}
              </p>
            );
          })}
        </div>
      </div>

      {instructions.map((instruction, instructionIndex) => (
        <p className="question-instruction" key={`instruction-${instructionIndex}`}>
          <FormattedMathText text={instruction} subject={subject} />
        </p>
      ))}

      {layout.stemRepeat && (
        <p className="question-stem-repeat" aria-hidden="true"><FormattedStem text={layout.stemRepeat} subject={subject} /></p>
      )}
    </>
  );
}

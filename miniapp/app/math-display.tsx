import {
  isImportantPromptSentence,
  mathDisplayParts,
  splitPromptSentences,
  tokenizeMathText,
} from "./math-text";

export function FormattedMathText({ text }: { text: string }) {
  return (
    <>
      {tokenizeMathText(text).map((part, partIndex) => (
        part.isMath
          ? (
            <span
              className={part.isVariable ? "math-expression math-variable" : "math-expression"}
              key={`${partIndex}-${part.text}`}
            >
              {mathDisplayParts(part.text).map((displayPart, displayIndex) => (
                displayPart.isSuperscript
                  ? <sup key={displayIndex}>{displayPart.text}</sup>
                  : displayPart.text
              ))}
            </span>
          )
          : part.text
      ))}
    </>
  );
}

export function FormattedStem({ text }: { text: string }) {
  return (
    <>
      {splitPromptSentences(text).map((sentence, sentenceIndex) => (
        <span
          className={isImportantPromptSentence(sentence)
            ? "prompt-sentence prompt-sentence-important"
            : "prompt-sentence"}
          key={`${sentenceIndex}-${sentence}`}
        >
          <FormattedMathText text={sentence} />
        </span>
      ))}
    </>
  );
}

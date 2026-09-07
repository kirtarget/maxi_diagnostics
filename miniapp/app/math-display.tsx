import {
  isImportantPromptSentence,
  mathDisplayParts,
  splitPromptSentences,
  tokenizeMathText,
} from "./math-text";

export function FormattedMathText({ text, subject }: { text: string; subject?: string }) {
  return (
    <>
      {tokenizeMathText(text, subject).map((part, partIndex) => (
        part.isMath
          ? (
            <span
              className={part.isVariable ? "math-expression math-variable" : "math-expression"}
              key={`${partIndex}-${part.text}`}
            >
              {mathDisplayParts(part.text).map((displayPart, displayIndex) => (
                displayPart.isSuperscript
                  ? <sup key={displayIndex}>{displayPart.text}</sup>
                  : displayPart.isSubscript
                    ? <sub key={displayIndex}>{displayPart.text}</sub>
                    : displayPart.text
              ))}
            </span>
          )
          : part.text
      ))}
    </>
  );
}

export function FormattedStem({ text, subject }: { text: string; subject?: string }) {
  return (
    <>
      {splitPromptSentences(text).map((sentence, sentenceIndex) => (
        <span
          className={isImportantPromptSentence(sentence)
            ? "prompt-sentence prompt-sentence-important"
            : "prompt-sentence"}
          key={`${sentenceIndex}-${sentence}`}
        >
          <FormattedMathText text={sentence} subject={subject} />
        </span>
      ))}
    </>
  );
}

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { FormattedMathText } from "./math-display";
import { updateCompactAnswer, updateMatchingAnswer } from "./answer-values";
import { cleanAnswerLabel } from "./question-prompt";
import { safeAssetPath } from "./question-assets";
import type { AnswerValue, MatchingQuestion } from "./types";
import type { SequenceMatchingPrompt } from "./sequence-matching";

export type MatchingSource = "matching" | "sequence";

export type MatchingCell = {
  key: string;
  marker: string;
  label: string;
  /** Set when the editor drew this cell instead of writing it. */
  asset?: string;
};

export type MatchingRow = MatchingCell;

export type MatchingOption = MatchingCell;

export type MatchingModel = {
  source: MatchingSource;
  rows: MatchingRow[];
  options: MatchingOption[];
  markers: string[];
  answerLength: number;
  allowReuse: boolean;
};

type MatchingAnswerProps = {
  model: MatchingModel;
  value: AnswerValue | undefined;
  subject?: string;
  disabled?: boolean;
  onChange: (value: AnswerValue) => void;
};

const MARKER = /^\s*([А-ЯЁA-Z0-9]+)(?:[).]|\s|$)/u;
// Latin letters an editor types where the КИМ prints Cyrillic. B is the shape
// of В, not of Б, which has no Latin lookalike at all.
const LOOKALIKE_CYRILLIC: Record<string, string> = {
  A: "А", B: "В", C: "С", E: "Е", K: "К", M: "М", H: "Н", O: "О", P: "Р", T: "Т", X: "Х", Y: "У",
};
const CHIP_LABEL_LIMIT = 3;
const SHEET_OPTION_LIMIT = 6;
const LONG_OPTION_LENGTH = 42;
const SEQUENCE_OPTION_LENGTH = 21;
const INLINE_OPTION_DENSITY_LIMIT = 90;
// Chips share one row, so each gets about a sixth of the screen. Past this the
// text inside them wraps into a tower instead of a chip.
const CHIP_TEXT_DENSITY_LIMIT = 30;
const CHIP_TEXT_LENGTH = 12;

function optionDensity(options: MatchingOption[]): number {
  return options.reduce((total, option) => total + option.marker.length + option.label.length, 0);
}

function shouldUseMatchingSheet(options: MatchingOption[]): boolean {
  return options.length > SHEET_OPTION_LIMIT
    || options.some((option) => option.label.length > LONG_OPTION_LENGTH)
    || (options.length >= 5 && optionDensity(options) > INLINE_OPTION_DENSITY_LIMIT);
}

/**
 * A chip that cannot hold its text carries the number instead. The wording it
 * drops is the wording of the list printed right above the rows, so nothing is
 * lost, and the student picks the digit the blank asks for.
 */
function shouldCompactChips(options: MatchingOption[]): boolean {
  return optionDensity(options) > CHIP_TEXT_DENSITY_LIMIT
    || options.some((option) => option.label.length > CHIP_TEXT_LENGTH);
}

// A drawn position carries its letter inside the picture, so the model has to
// name it. The КИМ run skips Ё.
const POSITION_MARKERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К", "Л", "М"];

function CellBody({ cell, subject }: { cell: MatchingCell; subject?: string }) {
  const figure = cell.asset ? safeAssetPath(cell.asset) : undefined;
  return (
    <span>
      {cell.label && <FormattedMathText text={cell.label} subject={subject} />}
      {figure && <img alt="" className="matching-answer-cell-figure" src={figure} />}
    </span>
  );
}

function displayParts(label: string, fallback: string): { marker: string; text: string } {
  const match = MARKER.exec(label);
  return {
    marker: match?.[1] ?? fallback,
    text: cleanAnswerLabel(label),
  };
}

function normalizeMarker(marker: string, subject?: string): string {
  const language = subject?.toLocaleLowerCase();
  const english = language?.includes("english") || language?.includes("англий");
  return english ? marker : LOOKALIKE_CYRILLIC[marker] ?? marker;
}

export function matchingModelFromQuestion(question: MatchingQuestion, subject?: string): MatchingModel {
  const rows = question.items.map((item, index) => {
    const parts = displayParts(item.label, POSITION_MARKERS[index] ?? String(index + 1));
    return {
      key: item.id,
      marker: normalizeMarker(parts.marker, subject),
      label: parts.text,
      asset: item.asset,
    };
  });
  const options = question.options.map((option, index) => {
    const parts = displayParts(option.label, String(index + 1));
    return {
      key: option.id,
      marker: normalizeMarker(parts.marker, subject),
      label: parts.text,
      asset: option.asset,
    };
  });
  return {
    source: "matching",
    rows,
    options,
    markers: rows.map((row) => row.marker),
    answerLength: rows.length,
    allowReuse: true,
  };
}

export function matchingModelFromSequence(matching: SequenceMatchingPrompt, subject?: string): MatchingModel {
  const rows = matching.left.slice(0, matching.answerLength).map((item) => ({
    key: item.marker,
    marker: normalizeMarker(item.marker, subject),
    label: item.label,
  }));
  const options = matching.options.map((option) => ({
    key: option.marker,
    marker: option.marker,
    label: option.label,
  }));
  return {
    source: "sequence",
    rows,
    options,
    markers: rows.map((row) => row.marker),
    answerLength: matching.answerLength,
    allowReuse: matching.allowReuse,
  };
}

function mapAnswer(value: AnswerValue | undefined): Record<string, string> {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** Fewer options than positions means the КИМ expects a digit to repeat. */
function repeatsExpected(model: MatchingModel): boolean {
  return model.options.length < model.rows.length;
}

export type MatchingReadiness = { isAnswered: boolean; reason: string };

/**
 * The button hint reads the markers the rows are drawn with. Deriving them a
 * second time is what sent students looking for a row «А» next to a circle «1».
 */
export function matchingReadiness(model: MatchingModel, value: AnswerValue | undefined): MatchingReadiness {
  const answer = mapAnswer(value);
  const selected = model.rows.map((row) => answer[row.key] ?? "");
  const missing = model.rows.filter((_, index) => !selected[index]).map((row) => row.marker);
  if (missing.length > 0) return { isAnswered: false, reason: `Осталось заполнить: ${missing.join(", ")}` };
  const duplicate = repeatsExpected(model)
    ? -1
    : selected.findIndex((key, index) => selected.indexOf(key) !== index);
  if (duplicate < 0) return { isAnswered: true, reason: "" };
  const marker = model.options.find((option) => option.key === selected[duplicate])?.marker ?? "";
  return { isAnswered: false, reason: `Вариант ${marker} выбран дважды` };
}

function selectedKey(model: MatchingModel, value: AnswerValue | undefined, sequenceSelections: string[], rowIndex: number): string {
  if (model.source === "matching") return mapAnswer(value)[model.rows[rowIndex]?.key] ?? "";
  return sequenceSelections[rowIndex] ?? "";
}

function selectedOptionMarker(model: MatchingModel, value: AnswerValue | undefined, sequenceSelections: string[], rowIndex: number): string {
  const key = selectedKey(model, value, sequenceSelections, rowIndex);
  return model.options.find((option) => option.key === key)?.marker ?? "";
}

function encodeSelection(
  model: MatchingModel,
  value: AnswerValue | undefined,
  sequenceSelections: string[],
  rowIndex: number,
  option: MatchingOption,
): AnswerValue {
  if (model.source === "matching") {
    return updateMatchingAnswer(mapAnswer(value), model.rows[rowIndex].key, option.key);
  }
  return updateCompactAnswer(typeof value === "string" ? value : sequenceSelections.slice(0, rowIndex).join(""), rowIndex, option.marker);
}

function clearSelection(
  model: MatchingModel,
  value: AnswerValue | undefined,
  sequenceSelections: string[],
  rowIndex: number,
): AnswerValue {
  if (model.source === "matching") {
    return updateMatchingAnswer(mapAnswer(value), model.rows[rowIndex].key, "");
  }
  return updateCompactAnswer(typeof value === "string" ? value : sequenceSelections.slice(0, rowIndex).join(""), rowIndex, "");
}

function compactPrefix(selections: string[]): string {
  const firstHole = selections.findIndex((selection) => !selection);
  return selections.slice(0, firstHole < 0 ? selections.length : firstHole).join("");
}

function radioTabIndex(selected: boolean, index: number, available: boolean[], selectedIndex: number): number {
  if (!available[index]) return -1;
  if (selected) return 0;
  if (selectedIndex >= 0) return -1;
  return index === available.findIndex(Boolean) ? 0 : -1;
}

function moveRadioFocus(
  event: ReactKeyboardEvent<HTMLButtonElement>,
  options: MatchingOption[],
  select: (option: MatchingOption) => void,
) {
  const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1
    : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1
    : 0;
  if (!delta) return;
  const group = event.currentTarget.closest('[role="radiogroup"]');
  if (!group) return;
  const controls = [...group.querySelectorAll<HTMLButtonElement>('[role="radio"]:not(:disabled)')];
  const current = controls.indexOf(event.currentTarget);
  if (current < 0 || controls.length === 0) return;
  event.preventDefault();
  const next = (current + delta + controls.length) % controls.length;
  const option = options.find((candidate) => candidate.key === controls[next].dataset.optionKey);
  if (!option) return;
  select(option);
  controls[next].focus();
}

function SequenceAnswer({ model, value, subject, disabled = false, onChange }: {
  model: MatchingModel;
  value: AnswerValue | undefined;
  subject?: string;
  disabled?: boolean;
  onChange: (value: AnswerValue) => void;
}) {
  const compactValue = typeof value === "string" ? value : "";
  const [selections, setSelections] = useState(() => [...compactValue]);
  const [activeRow, setActiveRow] = useState(() => Math.min(
    [...compactValue].length,
    Math.max(model.answerLength - 1, 0),
  ));
  const [sheetOpen, setSheetOpen] = useState(false);
  const cellRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const sheetOpener = useRef<HTMLElement | null>(null);
  const sheetRef = useRef<HTMLElement | null>(null);
  const lastEmitted = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (lastEmitted.current === compactValue) {
      lastEmitted.current = undefined;
      return;
    }
    setSelections([...compactValue]);
    setActiveRow(Math.min([...compactValue].length, Math.max(model.answerLength - 1, 0)));
  }, [compactValue, model.answerLength]);

  useEffect(() => {
    if (!sheetOpen) return;
    const sheet = sheetRef.current;
    const firstEnabled = sheet?.querySelector<HTMLButtonElement>('button[role="radio"][tabindex="0"]:not([disabled])');
    firstEnabled?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSheetOpen(false);
      if (event.key !== "Tab") return;
      const focusable = sheet
        ? [...sheet.querySelectorAll<HTMLElement>('button:not([disabled]):not([tabindex="-1"]), [href], input:not([disabled])')]
        : [];
      if (focusable.length < 2) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      const opener = sheetOpener.current;
      if (opener) opener.focus();
      else cellRefs.current[activeRow]?.focus();
      sheetOpener.current = null;
    };
  }, [activeRow, sheetOpen]);

  const selectedKeys = model.rows.map((_, index) => selections[index] ?? "");
  const usedBy = new Map<string, number>();
  selectedKeys.forEach((key, index) => {
    if (key && !usedBy.has(key)) usedBy.set(key, index);
  });
  const useSheet = model.options.length > SHEET_OPTION_LIMIT + 1
    || model.options.some((option) => option.label.length > SEQUENCE_OPTION_LENGTH);
  const firstEmpty = selectedKeys.findIndex((selection) => !selection);
  const filled = compactPrefix(selectedKeys).length;
  const selectOption = (option: MatchingOption) => {
    const targetRow = firstEmpty < 0
      ? Math.min(activeRow, Math.max(model.answerLength - 1, 0))
      : Math.min(activeRow, firstEmpty);
    const usedAt = usedBy.get(option.key);
    if (disabled || (usedAt !== undefined && usedAt !== targetRow && !model.allowReuse)) return;
    const next = [...selections];
    next[targetRow] = option.marker;
    setSelections(next);
    const prefix = compactPrefix(next);
    lastEmitted.current = prefix;
    onChange(prefix);
    return { targetRow, nextEmpty: next.findIndex((selection) => !selection) };
  };
  const choose = (option: MatchingOption) => {
    const result = selectOption(option);
    if (!result) return;
    const { targetRow, nextEmpty } = result;
    setActiveRow(nextEmpty >= 0 ? nextEmpty : Math.min(targetRow + 1, model.answerLength - 1));
    setSheetOpen(false);
  };
  const clearAll = () => {
    if (disabled) return;
    setSelections([]);
    setActiveRow(0);
    lastEmitted.current = "";
    onChange("");
  };
  const openSheet = (opener: HTMLElement) => {
    sheetOpener.current = opener;
    setSheetOpen(true);
  };
  const renderOption = (option: MatchingOption, index: number) => {
    const targetRow = firstEmpty < 0
      ? Math.min(activeRow, Math.max(model.answerLength - 1, 0))
      : Math.min(activeRow, firstEmpty);
    const selected = selectedKeys[targetRow] === option.key;
    const usedAt = usedBy.get(option.key);
    const blocked = usedAt !== undefined && usedAt !== targetRow && !model.allowReuse;
    const available = model.options.map((candidate) => {
      const used = usedBy.get(candidate.key);
      return !disabled && !(used !== undefined && used !== targetRow && !model.allowReuse);
    });
    const selectedIndex = model.options.findIndex((candidate) => candidate.key === selectedKeys[targetRow]);
    return (
      <button
        aria-checked={selected}
        aria-label={`${option.marker} — ${option.label}${blocked ? `, в строке ${model.rows[usedAt]?.marker ?? ""}` : ""}`}
        className={`matching-answer-option${selected ? " selected" : ""}`}
        data-option-key={option.key}
        disabled={disabled || blocked}
        key={option.key}
        onClick={() => choose(option)}
        onKeyDown={(event) => moveRadioFocus(event, model.options, selectOption)}
        role="radio"
        tabIndex={radioTabIndex(selected, index, available, selectedIndex)}
        type="button"
      >
        <strong>{option.marker}</strong>
        <CellBody cell={option} subject={subject} />
        {blocked && <small>в строке {model.rows[usedAt]?.marker ?? ""}</small>}
      </button>
    );
  };

  return (
    <section className="matching-answer matching-answer-sequence" aria-labelledby="sequence-answer-title">
      <div className="matching-answer-intro">
        <span>Ответ без ручного ввода</span>
        <h2 id="sequence-answer-title">Составь последовательность</h2>
        <p>Нажми на ячейку, затем выбери цифру.</p>
      </div>
      <div className="sequence-answer-cells" aria-label="Позиции ответа">
        {model.rows.map((row, index) => {
          const selected = selectedKeys[index];
          const isLaterEmpty = firstEmpty >= 0 && index > firstEmpty && !selected;
          return (
            <button
              aria-label={`Позиция ${row.marker}: ${row.label}${selected ? `, выбрано ${selected}` : ", не заполнено"}`}
              aria-pressed={activeRow === index}
              className={`sequence-answer-cell${selected ? " is-filled" : " is-empty"}${activeRow === index ? " is-active" : ""}`}
              data-sequence-cell={row.marker}
              disabled={disabled || isLaterEmpty}
              key={row.key}
              onClick={(event) => {
                if (isLaterEmpty) return;
                setActiveRow(index);
                if (useSheet) openSheet(event.currentTarget);
              }}
              ref={(element) => { cellRefs.current[index] = element; }}
              type="button"
            >
              <strong>{row.marker}</strong>
              <span>{selected || "—"}</span>
              <small>{row.label}</small>
            </button>
          );
        })}
      </div>
      <p className="sequence-answer-progress">Заполнено {filled} из {model.answerLength}</p>
      {!useSheet && (
        <div className="sequence-answer-palette" aria-label="Цифры для выбора" role="radiogroup">
          {model.options.map(renderOption)}
        </div>
      )}
      {useSheet && (
          <button
            className="matching-answer-trigger sequence-answer-sheet-trigger"
            aria-expanded={sheetOpen}
            aria-haspopup="dialog"
            disabled={disabled}
          onClick={(event) => openSheet(event.currentTarget)}
          type="button"
        >
          Открыть полный список вариантов для {model.rows[activeRow]?.marker}
        </button>
      )}
      <button className="matching-answer-clear sequence-answer-clear" disabled={disabled || filled === 0} onClick={clearAll} type="button">
        Очистить всё
      </button>
      {sheetOpen && useSheet && (
        <div className="matching-answer-sheet-backdrop" role="presentation" onClick={() => setSheetOpen(false)}>
          <section ref={sheetRef} className="matching-answer-sheet" data-sequence-sheet role="dialog" aria-modal="true" aria-labelledby="sequence-answer-sheet-title" onClick={(event) => event.stopPropagation()}>
            <h3 id="sequence-answer-sheet-title">Варианты для позиции {model.rows[activeRow]?.marker}</h3>
            <div className="matching-answer-sheet-options" aria-label={`Варианты для позиции ${model.rows[activeRow]?.marker}`} role="radiogroup">
              {model.options.map(renderOption)}
            </div>
            <button className="secondary-button" onClick={() => setSheetOpen(false)} type="button">Закрыть</button>
          </section>
        </div>
      )}
      <AnswerPreview markers={model.markers} selected={selectedKeys} />
    </section>
  );
}

function MapMatchingAnswer({ model, value, subject, disabled = false, onChange }: MatchingAnswerProps) {
  const [openRow, setOpenRow] = useState<number | null>(null);
  const triggerRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const sheetWasOpenedBy = openRow === null ? null : triggerRefs.current[openRow];
  const sheetRefs = useRef<Array<HTMLElement | null>>([]);

  useEffect(() => {
    if (openRow === null) return;
    const trigger = sheetWasOpenedBy;
    const sheet = sheetRefs.current[openRow];
    sheet?.querySelector<HTMLButtonElement>('button[role="radio"][tabindex="0"]:not([disabled])')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenRow(null);
      if (event.key !== "Tab") return;
      const focusable = sheet
        ? [...sheet.querySelectorAll<HTMLElement>('button:not([disabled]):not([tabindex="-1"]), [href], input:not([disabled])')]
        : [];
      if (focusable.length < 2) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      trigger?.focus();
    };
  }, [openRow, sheetWasOpenedBy]);

  const selectedKeys = model.rows.map((_, index) => selectedKey(model, value, [], index));
  const usedBy = new Map<string, number>();
  selectedKeys.forEach((key, index) => {
    if (key && !usedBy.has(key)) usedBy.set(key, index);
  });
  const useSheet = shouldUseMatchingSheet(model.options);
  const compactChips = shouldCompactChips(model.options);
  const repeatsAreNormal = repeatsExpected(model);
  const selectOption = (rowIndex: number, option: MatchingOption) => {
    const usedAt = usedBy.get(option.key);
    if (disabled || (usedAt !== undefined && usedAt !== rowIndex && !model.allowReuse)) return;
    onChange(encodeSelection(model, value, [], rowIndex, option));
    return true;
  };
  const choose = (rowIndex: number, option: MatchingOption) => {
    if (!selectOption(rowIndex, option)) return;
    setOpenRow(null);
  };
  const clear = (rowIndex: number) => {
    if (disabled) return;
    onChange(clearSelection(model, value, [], rowIndex));
  };
  const renderOption = (rowIndex: number, option: MatchingOption, index: number, inSheet = false) => {
    const selected = selectedKeys[rowIndex] === option.key;
    const usedAt = usedBy.get(option.key);
    const blocked = usedAt !== undefined && usedAt !== rowIndex && !model.allowReuse;
    const available = model.options.map((candidate) => {
      const used = usedBy.get(candidate.key);
      return !disabled && !(used !== undefined && used !== rowIndex && !model.allowReuse);
    });
    const selectedIndex = model.options.findIndex((candidate) => candidate.key === selectedKeys[rowIndex]);
    return (
      <button
        aria-checked={selected}
        aria-label={`${option.marker} — ${option.label}${blocked ? `, в строке ${model.rows[usedAt]?.marker ?? ""}` : ""}`}
        className={`matching-answer-option${selected ? " selected" : ""}${compactChips && !inSheet ? " compact" : ""}`}
        data-option-key={option.key}
        disabled={disabled || blocked}
        key={option.key}
        onClick={() => choose(rowIndex, option)}
        onKeyDown={(event) => moveRadioFocus(event, model.options, (selectedOption) => selectOption(rowIndex, selectedOption))}
        role="radio"
        tabIndex={radioTabIndex(selected, index, available, selectedIndex)}
        type="button"
      >
        <strong>{option.marker}</strong>
        {!(compactChips && !inSheet) && <CellBody cell={option} subject={subject} />}
        {blocked && <small>в строке {model.rows[usedAt]?.marker ?? ""}</small>}
        {inSheet && selected && <small>выбрано</small>}
      </button>
    );
  };

  return (
    <section className={`matching-answer matching-answer-${model.source}`} aria-labelledby="matching-answer-title">
      <div className="matching-answer-intro">
        <span>Ответ без ручного ввода</span>
        <h2 id="matching-answer-title">Установи соответствие</h2>
        <p>Для каждого пункта выбери подходящий вариант.</p>
      </div>
      <div className="matching-answer-option-list" aria-label="Список вариантов" role="list">
        {model.options.map((option) => (
          <div className="matching-answer-option-reference" key={option.key} role="listitem">
            <strong>{option.marker}</strong>
            <CellBody cell={option} subject={subject} />
          </div>
        ))}
      </div>
      <div className="matching-answer-rows">
        {model.rows.map((row, rowIndex) => {
          const selectedMarker = selectedOptionMarker(model, value, [], rowIndex);
          const selectedOption = model.options.find((option) => option.marker === selectedMarker);
          const duplicateAt = repeatsAreNormal
            ? -1
            : selectedKeys.findIndex((key, index) => index !== rowIndex && key && key === selectedKeys[rowIndex]);
          return (
            <div
              className={`matching-answer-row${selectedMarker ? " is-filled" : " is-empty"}`}
              data-state={selectedMarker ? "filled" : "empty"}
              key={row.key}
            >
              <div className="matching-answer-row-copy"><strong>{row.marker}</strong><CellBody cell={row} subject={subject} /></div>
              {useSheet ? (
                <button
                  aria-expanded={openRow === rowIndex}
                  aria-haspopup="dialog"
                  className="matching-answer-trigger"
                  disabled={disabled}
                  onClick={() => setOpenRow(rowIndex)}
                  ref={(element) => { triggerRefs.current[rowIndex] = element; }}
                  type="button"
                >
                  {selectedMarker && selectedOption ? <><strong>{selectedMarker}</strong> <CellBody cell={selectedOption} subject={subject} /></> : "Выбери вариант"}
                </button>
              ) : (
                <div className="matching-answer-options" aria-label={`Варианты для пункта ${row.marker}`} role="radiogroup">
                  {model.options.map((option, index) => renderOption(rowIndex, option, index))}
                </div>
              )}
              {selectedMarker && <button className="matching-answer-clear" disabled={disabled} onClick={() => clear(rowIndex)} type="button">Очистить</button>}
              {duplicateAt >= 0 && <small className="matching-answer-duplicate" role="alert">Вариант {selectedMarker} уже выбран в строке {model.rows[duplicateAt].marker}</small>}
              {useSheet && openRow === rowIndex && (
                <div className="matching-answer-sheet-backdrop" role="presentation" onClick={() => setOpenRow(null)}>
                  <section ref={(element) => { sheetRefs.current[rowIndex] = element; }} className="matching-answer-sheet" data-matching-sheet-row={rowIndex} role="dialog" aria-modal="true" aria-labelledby={`matching-answer-sheet-title-${rowIndex}`} onClick={(event) => event.stopPropagation()}>
                    <h3 id={`matching-answer-sheet-title-${rowIndex}`}>Варианты для {row.marker}</h3>
                    <div className="matching-answer-sheet-options" aria-label={`Варианты для пункта ${row.marker}`} role="radiogroup">
                      {model.options.map((option, index) => renderOption(rowIndex, option, index, true))}
                    </div>
                    <button className="secondary-button" onClick={() => setOpenRow(null)} type="button">Закрыть</button>
                  </section>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <AnswerPreview markers={model.markers} selected={model.rows.map((_, index) => selectedOptionMarker(model, value, [], index))} />
    </section>
  );
}

export function MatchingAnswer({ model, value, subject, disabled = false, onChange }: MatchingAnswerProps) {
  return model.source === "sequence"
    ? <SequenceAnswer model={model} value={value} subject={subject} disabled={disabled} onChange={onChange} />
    : <MapMatchingAnswer model={model} value={value} subject={subject} disabled={disabled} onChange={onChange} />;
}

export function AnswerPreview({ markers, selected, label = "Твой ответ", compare }: {
  markers: string[];
  selected: string[];
  label?: string;
  /** Row to compare against position by position. Positions that differ are marked. */
  compare?: string[];
}) {
  const values = markers.map((_, index) => selected[index] ?? "");
  // The chip that carries this label is one character wide. A cell named by a
  // table heading is written out in the rows above, so here it is its position.
  const chips = markers.map((marker, index) =>
    marker.trim().length <= CHIP_LABEL_LIMIT ? marker : String(index + 1),
  );
  return (
    <div className={`matching-answer-preview${values.length > 0 && values.every(Boolean) ? " complete" : ""}`}>
      <span>{label}</span>
      <strong>
        {markers.map((marker, index) => (
          <span
            key={`${marker}-${index}`}
            className={compare && values[index] !== (compare[index] ?? "") ? "is-mismatch" : undefined}
          >
            {values[index] || "—"}<small>{chips[index]}</small>
          </span>
        ))}
      </strong>
    </div>
  );
}

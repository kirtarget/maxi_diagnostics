"use client";

import { useEffect, useRef } from "react";

export type ConfirmSheetProps = {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
  title?: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmDisabled?: boolean;
  messageRole?: "alert";
};

export function ConfirmSheet({ open, onCancel, onConfirm, title = "Выйти из тренировки?", message = "Прогресс текущего вопроса не сохранится.", confirmLabel = "Выйти", cancelLabel = "Остаться", confirmDisabled = false, messageRole }: ConfirmSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const onCancelRef = useRef(onCancel);
  const onConfirmRef = useRef(onConfirm);
  onCancelRef.current = onCancel;
  onConfirmRef.current = onConfirm;

  const restoreFocus = () => {
    const element = returnFocusRef.current;
    returnFocusRef.current = null;
    if (element?.isConnected) element.focus();
  };

  useEffect(() => {
    if (!open) return;

    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const sheet = sheetRef.current;
    const focusable = () => Array.from(sheet?.querySelectorAll<HTMLElement>(
      "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
    ) ?? []).filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
    focusable()[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current();
        return;
      }
      if (event.key !== "Tab" || !sheet) return;
      const elements = focusable();
      if (elements.length === 0) {
        event.preventDefault();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (!sheet.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      restoreFocus();
    };
  }, [open]);

  const cancel = () => {
    onCancelRef.current();
  };

  const confirm = () => {
    onConfirmRef.current();
  };

  if (!open) return null;
  return (
    <div className="confirm-sheet-backdrop" role="presentation" onClick={cancel}>
      <section
        className="confirm-sheet"
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-sheet-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="confirm-sheet-title">{title}</h2>
        <p role={messageRole}>{message}</p>
        <div className="confirm-sheet-actions">
          <button className="secondary-button" type="button" onClick={cancel}>{cancelLabel}</button>
          <button className="primary-button" type="button" disabled={confirmDisabled} aria-busy={confirmDisabled || undefined} onClick={confirm}>{confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { safeAssetPath } from "./question-assets";

export type ImageAsset = {
  path: string;
  alt?: string | null;
};

export type ImageViewerProps = {
  assets: readonly ImageAsset[];
  fallbackAlt: string;
  className?: string;
};

const MIN_ZOOM = 1;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;

function imageAlt(asset: ImageAsset, fallbackAlt: string, index: number, count: number): string {
  const alt = asset.alt?.trim();
  if (alt) return alt;
  return count > 1 ? `${fallbackAlt} ${index + 1}` : fallbackAlt;
}

export function ImageViewer({ assets, fallbackAlt, className = "" }: ImageViewerProps) {
  const safeAssets = assets.flatMap((asset) => {
    const path = safeAssetPath(asset.path);
    return path ? [{ ...asset, path }] : [];
  });
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (openIndex === null) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpenIndex(null);
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      )).filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!dialog.contains(document.activeElement)) {
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
      document.body.style.overflow = previousOverflow;
      const trigger = returnFocusRef.current;
      returnFocusRef.current = null;
      if (trigger?.isConnected) trigger.focus();
    };
  }, [openIndex]);

  useEffect(() => {
    if (openIndex !== null) setZoom(MIN_ZOOM);
  }, [openIndex]);

  if (safeAssets.length === 0) return null;
  const openedAsset = openIndex === null ? null : safeAssets[openIndex];

  return (
    <div className={`image-viewer ${className}`.trim()}>
      {safeAssets.map((asset, index) => (
        <div className="image-viewer-item" key={`${asset.path}-${index}`}>
          <button
            className="image-viewer-trigger"
            type="button"
            aria-label={`${imageAlt(asset, fallbackAlt, index, safeAssets.length)}. Нажми, чтобы увеличить`}
            onClick={() => setOpenIndex(index)}
          >
            {/* Assets are validated by safeAssetPath before they reach the browser. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="image-viewer-inline" src={asset.path} alt={imageAlt(asset, fallbackAlt, index, safeAssets.length)} />
            <span className="image-viewer-hint">Нажми, чтобы увеличить</span>
          </button>
        </div>
      ))}
      {openedAsset && openIndex !== null && (
        <div className="image-viewer-backdrop" role="presentation" onClick={() => setOpenIndex(null)}>
          <section
            className="image-viewer-dialog"
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={imageAlt(openedAsset, fallbackAlt, openIndex, safeAssets.length)}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="image-viewer-dialog-toolbar">
              <button
                className="image-viewer-close"
                type="button"
                ref={closeRef}
                aria-label="Закрыть изображение"
                onClick={() => setOpenIndex(null)}
              >
                ×
              </button>
              <div className="image-viewer-zoom-controls" aria-label="Масштаб изображения">
                <button type="button" className="image-viewer-zoom-control" aria-label="Уменьшить" disabled={zoom <= MIN_ZOOM} onClick={() => setZoom((value) => Math.max(MIN_ZOOM, value - ZOOM_STEP))}>−</button>
                <span aria-live="polite">{Math.round(zoom * 100)}%</span>
                <button type="button" className="image-viewer-zoom-control" aria-label="Увеличить" disabled={zoom >= MAX_ZOOM} onClick={() => setZoom((value) => Math.min(MAX_ZOOM, value + ZOOM_STEP))}>+</button>
              </div>
            </div>
            <div className="image-viewer-dialog-viewport">
              {/* Native touch pinch-zoom is enabled by the viewport CSS; controls cover non-touch devices. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                className="image-viewer-dialog-image"
                src={openedAsset.path}
                alt={imageAlt(openedAsset, fallbackAlt, openIndex, safeAssets.length)}
                style={{ transform: `scale(${zoom})` } satisfies CSSProperties}
              />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import type { Point } from "../views/MapEdit";
import type { Sticky } from "../notes";
import { Icon } from "./Icon";
import "./sticky.css";

export const STICKY_W = 190;

/** A sticky note drawn on the canvas overlay: scaled with the map's zoom, dragged by its top strip, typed into directly. */
export function StickyNote({
  note,
  at,
  zoom,
  autoFocus,
  onChange,
  onMoveEnd,
  onDelete,
  onDiscard,
}: {
  note: Sticky;
  at: Point;
  zoom: number;
  autoFocus: boolean;
  onChange: (text: string) => void;
  onMoveEnd: (dx: number, dy: number) => void; // in flow units
  onDelete: () => void;
  onDiscard: () => void; // left empty: drop it without an undo toast
}) {
  const [drag, setDrag] = useState<Point | null>(null);
  const start = useRef<Point | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (autoFocus) area.current?.focus();
  }, [autoFocus]);
  // Grow with the text; the note has no fixed height.
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [note.text]);
  return (
    <div
      className={`sticky ${drag ? "dragging" : ""}`}
      style={{ left: at.x + (drag?.x ?? 0), top: at.y + (drag?.y ?? 0), width: STICKY_W, transform: `scale(${zoom})` }}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      <div
        className="sticky-bar"
        onPointerDown={(e) => {
          if ((e.target as HTMLElement).closest("button")) return;
          start.current = { x: e.clientX, y: e.clientY };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (start.current) setDrag({ x: (e.clientX - start.current.x) / zoom, y: (e.clientY - start.current.y) / zoom });
        }}
        onPointerUp={() => {
          if (drag) onMoveEnd(drag.x, drag.y);
          start.current = null;
          setDrag(null);
        }}
        onPointerCancel={() => ((start.current = null), setDrag(null))}
      >
        <span className="sticky-kicker">Note</span>
        <button className="sticky-x" title="Delete note" aria-label="Delete note" onClick={onDelete}>
          <Icon name="trash" size={13} />
        </button>
      </div>
      <textarea
        ref={area}
        className="sticky-text"
        rows={2}
        value={note.text}
        placeholder="Note…"
        aria-label="Sticky note"
        onChange={(e) => onChange(e.target.value)}
        onBlur={() => !note.text.trim() && onDiscard()}
        onKeyDown={(e) => e.key === "Escape" && e.currentTarget.blur()}
      />
    </div>
  );
}

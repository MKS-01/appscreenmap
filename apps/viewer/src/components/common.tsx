import { useState } from "react";
import { runFile } from "../api";
import { Icon } from "./Icon";
import { screenHref } from "../router";
import type { RunMeta, Screen } from "../types";

export function StatusBadge({ status }: { status: RunMeta["status"] | string }) {
  return (
    <span className={`badge ${status}`}>
      <span className="dot" style={{ background: status === "running" ? undefined : "currentColor" }} />
      {status}
    </span>
  );
}

export function Thumb({ run, screen, className }: { run: string; screen: Screen | undefined; className?: string }) {
  if (!screen?.thumb) return <div className={`noimg ${className ?? ""}`} />;
  return <img className={className} src={runFile(run, screen.thumb)} alt={screen.title} loading="lazy" />;
}

export function ScreenLink({ run, screen, children }: { run: string; screen: Screen | undefined; children?: React.ReactNode }) {
  if (!screen) return <span className="faint">—</span>;
  return (
    <a href={screenHref(run, screen.id)} title={screen.id}>
      {children ?? (
        <>
          <span className="sid">{screen.kind === "app" ? screen.id : "ext"}</span> {screen.title}
        </>
      )}
    </a>
  );
}

export function CopyButton({ text, label = "Copy", iconOnly }: { text: string; label?: string; iconOnly?: boolean }) {
  const [done, setDone] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setDone(true);
    setTimeout(() => setDone(false), 1400);
  };
  if (iconOnly)
    return (
      <button className="btn icon-only" onClick={copy} aria-label={done ? "Copied" : label} title={done ? "Copied" : label}>
        <Icon name={done ? "check" : "copy"} size={14} />
      </button>
    );
  return (
    <button className="btn" onClick={copy}>
      {done ? "Copied ✓" : label}
    </button>
  );
}

export function Stat({ value, label, title }: { value: React.ReactNode; label: string; title?: string }) {
  return (
    <div className="panel stat" title={title}>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

export const Loading = () => <div className="empty">Loading…</div>;
export const ErrorBox = ({ error }: { error: string }) => <div className="error">Couldn't load: {error}</div>;

export function Logo() {
  // Project mark D, "stacked screens": one screen leading to the next. Colours are tokens; the favicon in
  // index.html repeats the same shape in hex.
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" style={{ fill: "var(--accent)" }} />
      <rect x="6" y="9" width="11" height="17" rx="2.4" style={{ fill: "var(--bg)", opacity: 0.45 }} />
      <rect x="15" y="6" width="11" height="17" rx="2.4" style={{ fill: "var(--bg)" }} />
    </svg>
  );
}

import { screenHref } from "../router";
import type { AuditChart, ChartDatum, Tone } from "./types";

// Small, dependency-free charts for Insights. Every value is directly labelled (tooltips only repeat it), one hue
// per series (accent), and status tones only where a value really is good / needs attention / bad, always with a
// legend word next to the colour. Marks: thin bars with a rounded data end and a square baseline, hairline axes.

const TONE_COLOR: Record<Tone, string> = { good: "var(--st-done)", warn: "var(--st-pending)", bad: "var(--st-blocked)", info: "var(--st-unreachable)" };
export const toneColor = (t?: Tone) => (t ? TONE_COLOR[t] : "var(--accent)");
export const TONE_WORD: Record<Tone, string> = { good: "good", warn: "needs attention", bad: "problem", info: "info" };

const fmt = (n: number) => (Math.abs(n) >= 10000 ? `${(n / 1000).toFixed(n >= 100000 ? 0 : 1)}K` : n.toLocaleString());

export function Chart({ chart, run }: { chart: AuditChart; run: string }) {
  return (
    <figure className="chart">
      <figcaption className="chart-head">
        <b>{chart.title}</b>
        {chart.note && <span className="faint small">{chart.note}</span>}
        {chart.sample && <SampleTag />}
      </figcaption>
      {chart.data.length === 0 ? (
        <div className="small muted">No data.</div>
      ) : chart.type === "bars" ? (
        <Bars data={chart.data} unit={chart.unit} budget={chart.budget} budgetLabel={chart.budgetLabel} run={run} />
      ) : chart.type === "columns" ? (
        <Columns data={chart.data} unit={chart.unit} />
      ) : (
        <Split data={chart.data} />
      )}
      {chart.type !== "split" && <ToneLegend data={chart.data} />}
    </figure>
  );
}

export const SampleTag = ({ label = "sample" }: { label?: string }) => (
  <span className="sample-tag" title="Placeholder data so the view can be built before this audit exists">
    {label}
  </span>
);

function ToneLegend({ data }: { data: ChartDatum[] }) {
  const tones = (["good", "warn", "bad", "info"] as Tone[]).filter((t) => data.some((d) => d.tone === t));
  if (!tones.length) return null;
  return (
    <div className="legend chart-legend">
      {tones.map((t) => (
        <span key={t}>
          <i className="dot" style={{ background: toneColor(t) }} aria-hidden /> {TONE_WORD[t]}
        </span>
      ))}
    </div>
  );
}

/** Horizontal bars, one row per item, value at the tip; an optional budget line across all rows. */
export function Bars({ data, unit, budget, budgetLabel, run }: { data: ChartDatum[]; unit?: string; budget?: number; budgetLabel?: string; run?: string }) {
  const max = Math.max(1, budget ?? 0, ...data.map((d) => d.value)) * 1.04;
  const pos = (v: number) => `${(100 * v) / max}%`;
  return (
    <div className="bars" role="list">
      {budget != null && (
        <div className="bars-budget" style={{ left: `calc(var(--bars-label) + var(--bars-gap) + (100% - var(--bars-label) - var(--bars-gap) - var(--bars-value) - var(--bars-gap)) * ${budget / max})` }}>
          <span className="faint">{budgetLabel ?? fmt(budget)}</span>
        </div>
      )}
      {data.map((d, k) => {
        const label = (
          <span className="bars-label ellipsis" title={d.label}>
            {d.label}
          </span>
        );
        const text = `${d.label}: ${fmt(d.value)}${unit ? ` ${unit}` : ""}${d.tone ? ` (${TONE_WORD[d.tone]})` : ""}${d.hint ? ` · ${d.hint}` : ""}`;
        return (
          <div key={k} className="bars-row" role="listitem" title={text} aria-label={text}>
            {d.screen && run ? <a href={screenHref(run, d.screen)}>{label}</a> : label}
            <span className="bars-track">
              <span className="bars-fill" style={{ width: pos(d.value), background: toneColor(d.tone) }} />
            </span>
            <span className="bars-value mono">
              {fmt(d.value)}
              {unit && <span className="faint"> {unit}</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Vertical columns for ordered categories; value on the cap. `highlight` emphasises one column, greys the rest. */
export function Columns({ data, unit, highlight }: { data: ChartDatum[]; unit?: string; highlight?: number }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="cols" role="list" style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}>
      {data.map((d, k) => {
        const text = `${d.label}: ${fmt(d.value)}${unit ? ` ${unit}` : ""}${d.hint ? ` · ${d.hint}` : ""}`;
        const muted = highlight != null && highlight !== k;
        return (
          <div key={k} className="col-item" role="listitem" title={text} aria-label={text}>
            <span className="col-plot">
              <span className="col-value mono">{fmt(d.value)}</span>
              <span
                className="col-bar"
                style={{
                  height: `${Math.max(d.value ? 3 : 0, (100 * d.value) / max)}%`,
                  background: muted ? "var(--border)" : toneColor(d.tone),
                }}
              />
            </span>
            <span className="col-label small muted ellipsis">{d.label}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Parts of one whole: a single stacked bar with 2px gaps, then a legend that carries every value. */
export function Split({ data }: { data: ChartDatum[] }) {
  const parts = data.filter((d) => d.value > 0);
  const total = parts.reduce((a, d) => a + d.value, 0);
  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="stack split-bar" role="img" aria-label={parts.map((d) => `${d.label} ${d.value}`).join(", ")}>
        {parts.map((d, k) => (
          <div key={k} style={{ width: `${(100 * d.value) / Math.max(1, total)}%`, background: toneColor(d.tone) }} title={`${d.label}: ${d.value}`} />
        ))}
      </div>
      <div className="legend">
        {parts.map((d, k) => (
          <span key={k}>
            <i className="dot" style={{ background: toneColor(d.tone) }} aria-hidden /> <b className="mono">{d.value}</b> {d.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Score 0–100 as a meter; the fill carries the tone, the track is the same hue lighter. */
export function Meter({ score, label, tone: given }: { score: number | null; label?: string; tone?: Tone }) {
  if (score == null) return null;
  const tone: Tone = given ?? (score >= 90 ? "good" : score >= 70 ? "warn" : "bad");
  return (
    <span className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-label={label ?? "score"} style={{ ["--tone" as string]: toneColor(tone) }}>
      <span style={{ width: `${score}%` }} />
    </span>
  );
}

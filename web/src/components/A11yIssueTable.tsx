import { SEVERITY_COLOR, TRIAGE_LABEL, useRules, type A11yIssue, type TriageStatus } from "../a11y";
import type { A11yTriage, RunTriage, TriagePatch } from "../notes";

const ORDER: TriageStatus[] = ["confirmed", "wontfix", "false_positive"];

export function statusOf(triage: RunTriage, issue: A11yIssue): TriageStatus {
  return (triage[issue.key] as A11yTriage | undefined)?.status ?? "open";
}

export default function A11yIssueTable({
  issues,
  triage,
  onTriage,
  hover,
  setHover,
}: {
  issues: A11yIssue[];
  triage: RunTriage;
  onTriage: (key: string, patch: TriagePatch) => void;
  hover?: string | null;
  setHover?: (key: string | null) => void;
}) {
  const RULES = useRules();
  if (!issues.length) return <div className="small muted" style={{ padding: 12 }}>No issues.</div>;
  return (
    <div className="tbl-scroll">
    <table className="tbl a11y-tbl">
      <thead>
        <tr>
          <th>Issue</th>
          <th>Element</th>
          <th>Review</th>
        </tr>
      </thead>
      <tbody>
        {issues.map((i) => {
          const t = triage[i.key] as A11yTriage | undefined; // Record index types never include undefined
          const status: TriageStatus = t?.status ?? "open";
          return (
            <tr
              key={i.key}
              className={`hover ${hover === i.key ? "sel" : ""} ${status === "false_positive" ? "fp" : ""}`}
              onMouseEnter={() => setHover?.(i.key)}
              onMouseLeave={() => setHover?.(null)}
            >
              <td style={{ minWidth: 170 }}>
                <span className="row" style={{ gap: 6 }}>
                  <i className="dot" style={{ background: SEVERITY_COLOR[i.severity] }} aria-hidden />
                  <span className="sr-only">{i.severity}:</span>
                  <b title={RULES[i.rule].why}>{RULES[i.rule].title}</b>
                </span>
                <div className="small faint">{i.detail}</div>
              </td>
              <td style={{ maxWidth: 260 }}>
                <div className="ellipsis" title={i.label}>
                  {i.label}
                </div>
                <div className="mono faint ellipsis" style={{ fontSize: 11 }} title={i.rid || i.cls}>
                  {i.rid ? i.rid.replace(/^.*?:id\//, "id/") : i.cls.replace(/^.*\./, "")}
                </div>
              </td>
              <td style={{ minWidth: 250 }}>
                <div className="seg" role="group" aria-label={`Review ${RULES[i.rule].title} on ${i.label}`}>
                  {ORDER.map((s) => (
                    <button
                      key={s}
                      className={status === s ? "on" : ""}
                      aria-pressed={status === s}
                      onClick={() => onTriage(i.key, { status: status === s ? "open" : s })}
                    >
                      {TRIAGE_LABEL[s]}
                    </button>
                  ))}
                </div>
                {status !== "open" && (
                  <input
                    type="text"
                    className="triage-note"
                    placeholder="Note (ticket, reason…)"
                    aria-label="Review note"
                    value={t?.note ?? ""}
                    onChange={(e) => onTriage(i.key, { note: e.target.value })}
                  />
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}

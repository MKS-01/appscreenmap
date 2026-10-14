// One shape for every audit the Insights tab shows: coverage, accessibility, performance, adaptive UI, store policy,
// platform changes, security, and whatever comes next. Mirrors `audits/<id>.json` in docs/MAP_SCHEMA.md, so a new
// tool (jadx, frida, an LLM reviewer) only has to write that file; the viewer renders it without code changes.

export type Severity = "error" | "warning" | "info";
export type AuditStatus = "pass" | "warn" | "fail" | "info" | "not_run";
export type Platform = "android" | "ios" | "both";
/** Tone of a metric or bar: good / needs attention / bad / informational. Absent = neutral (accent). */
export type Tone = "good" | "warn" | "bad" | "info";

/** Where a report came from. `sample` is placeholder data so the UI can be built before the audit exists. */
export type AuditSource = "run" | "sample" | "mixed" | "none";

export interface AuditRef {
  title: string;
  url: string;
  publisher?: string; // "Android Developers", "Apple Developer", "Google Play", "W3C"
  date?: string; // ISO date the source was published or last checked
}

export interface AuditFinding {
  id: string;
  severity: Severity;
  title: string;
  detail?: string;
  fix?: string;
  screen?: string; // map.json screen id, linked in the viewer
  platform?: Platform;
  category?: string; // free-form group within an audit, e.g. "Manifest", "Network", "Large screens"
  due?: string; // ISO date: a store or platform deadline this finding is tied to
  refs?: AuditRef[];
  sample?: boolean; // placeholder finding inside a report that is otherwise real
  inferred?: boolean; // viewer-only: `platform` was filled in from the crawled platform, not written by the audit
  /** A store or platform requirement's state, shown as a met / due / blocked / upcoming / not-checked glyph. */
  requirement?: Requirement;
}

export type Requirement = "met" | "due" | "blocked" | "upcoming" | "not_checked";

export interface AuditMetric {
  label: string;
  value: number | string;
  unit?: string;
  tone?: Tone;
  hint?: string;
  sample?: boolean;
}

export interface ChartDatum {
  label: string;
  value: number;
  tone?: Tone;
  screen?: string;
  hint?: string;
}

/** Declarative charts, so an audit file can ship its own without viewer changes. */
interface ChartBase {
  title: string;
  note?: string;
  unit?: string;
  sample?: boolean;
  data: ChartDatum[];
}
export type AuditChart =
  | (ChartBase & { type: "bars"; budget?: number; budgetLabel?: string }) // one row per item, sorted by caller
  | (ChartBase & { type: "columns" }) // ordered categories: depth, size class, run
  | (ChartBase & { type: "split" }); // parts of one whole, e.g. issues by severity

export interface AuditReport {
  schema: 1;
  audit: string; // id, also the file name: audits/<id>.json
  title: string;
  tool?: string; // what produced it: "appscreenmap 0.1.0", "jadx 1.5.1 + frida 17"
  generated_at?: string;
  source: AuditSource;
  status: AuditStatus;
  score: number | null; // 0–100, higher is better; null when the audit doesn't score
  score_note?: string; // how the score is computed, in one sentence
  status_label?: string; // a plainer word than the status when one fits: "Partial", "Blocked for Play updates"
  summary: string;
  metrics: AuditMetric[];
  charts: AuditChart[];
  findings: AuditFinding[];
  refs: AuditRef[]; // official docs the audit's checks follow
}

/** A check an audit will run once it is set up. Shown as a placeholder while it isn't. */
export interface PlannedCheck {
  id?: string;
  title: string;
  detail: string; // what it looks at and why it matters, one or two sentences
  fix?: string;
  severity?: Severity;
  category?: string; // group heading, e.g. "Manifest and Info.plist"
  platform?: Platform;
  needs?: string; // what has to exist first: "jadx", "frida", "the APK's manifest"
  refs?: AuditRef[];
}

/** What the registry knows about an audit before any data loads. */
export interface AuditDef {
  id: string;
  title: string;
  group: "crawl" | "release"; // "From this crawl" vs "Release readiness"
  qualifier?: string; // small mono tag after the title, e.g. "WCAG 2.2"
  icon: import("../components/Icon").IconName;
  blurb: string; // what it checks, one line
  produces: string; // what will produce real data, for "not run" states
  /** "ready": the viewer can build it from run files, so "not run" means this crawl lacks them. "planned": the checks
   *  below don't exist yet, so the audit is "not set up" and lists what it will do. */
  setup?: "ready" | "planned";
  planned?: PlannedCheck[];
  enable?: string[]; // commands or steps that turn it on, when known
}

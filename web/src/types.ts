// Mirrors map.json schema 1 written by src/appscreenmap/model.py.

export type ElementStatus = "pending" | "done" | "blocked" | "skipped" | "failed" | "unreachable";
export type Effect = "new_screen" | "known_screen" | "same_screen" | "left_app" | "crash" | "not_found";

export interface Selector {
  id?: string;
  text?: string;
  desc?: string;
  point?: [number, number];
}

export interface Step {
  screen: string;
  key: string;
  action: string;
  label: string;
  selector: Selector;
  scroll_depth: number;
}

export interface UIElement {
  id: string;
  key: string;
  kind: string;
  action: string;
  label: string;
  class: string;
  rid: string;
  text: string;
  desc: string;
  hint: string;
  bounds: [number, number, number, number];
  group: string | null;
  password: boolean;
  checked: boolean | null;
  direction: string | null;
  status: ElementStatus;
  effect: Effect | null;
  target: string | null;
  scroll_depth: number;
  note?: string;
}

export interface Screen {
  id: string;
  kind: "app" | "external" | "crash";
  title: string;
  activity: string | null;
  package: string | null;
  signature: string;
  patterns: string[];
  depth: number;
  visits: number;
  first_step: number;
  /** How the screen is reached: launch = app start lands here; action = reach_path replays from launch;
   *  unknown = no recorded path. Absent in runs made before the crawler recorded it. */
  origin?: "launch" | "action" | "unknown";
  width: number;
  height: number;
  screenshot: string | null;
  thumb: string | null;
  hierarchy: string | null;
  reach_path: Step[];
  autofill: { key: string; label: string; value: string; selector?: Selector }[];
  tokens: string[];
  elements: UIElement[];
}

export interface Transition {
  id: string;
  from: string;
  to: string;
  key: string;
  action: string;
  label: string;
  kind: string;
  count: number;
  step: number;
}

export interface RunEvent {
  step: number;
  type: "crash" | "permission" | "restart" | "nav_failed" | string;
  detail: string;
  screen?: string | null;
  log?: string | null;
}

export interface AppInfo {
  package: string;
  label?: string;
  version?: string;
  launch_activity?: string;
  activities?: string[];
  orientation_locked?: Record<string, string>; // activity → locked orientation, from the manifest
}

export interface DeviceInfo {
  serial?: string;
  model?: string;
  manufacturer?: string;
  android?: string;
  sdk?: string;
  width?: number;
  height?: number;
  density?: number; // dpi
  font_scale?: number;
  // Richer device record (crawler device.py); absent on older runs. See docs/MAP_SCHEMA.md "device".
  platform?: "android" | "ios";
  type?: "emulator" | "physical";
  name?: string;
  form_factor?: string;
  os?: { name?: string; release?: string; sdk?: number; skin?: string | null; security_patch?: string };
  display?: { width_dp?: number; height_dp?: number; smallest_width_dp?: number; window_class?: "compact" | "medium" | "expanded" };
  settings?: { locale?: string; dark_mode?: boolean | null; navigation?: string; talkback?: boolean };
}

export interface RunMeta {
  id: string;
  status: "running" | "done" | "failed" | "stopped";
  started_at: string;
  finished_at: string | null;
  tool?: string;
  app: AppInfo;
  device: DeviceInfo;
  config: Record<string, unknown>;
  steps?: number;
  elapsed_s?: number;
  error?: string;
}

export interface Stats {
  screens: number;
  external: number;
  transitions: number;
  max_depth: number;
  activities_visited: string[];
  activities_declared: number;
  activity_coverage: number | null;
  crashes: number;
  elements: Partial<Record<ElementStatus, number>>;
}

export interface AppMapData {
  schema: number;
  run: RunMeta;
  screens: Screen[];
  transitions: Transition[];
  events: RunEvent[];
  stats: Stats;
}

export interface RunIndexRow {
  id: string;
  project?: string; // runs/<project>/<id>/ layout
  path?: string; // run folder relative to runs/; absent for legacy runs/<id>/ folders
  status: RunMeta["status"];
  started_at: string;
  finished_at: string | null;
  app: AppInfo;
  device: DeviceInfo;
  steps: number | null;
  elapsed_s: number | null;
  screens: number;
  transitions: number;
  crashes: number;
  thumb: string | null;
  diffs: string[];
}

// One line of trace.jsonl: either an action that ran, or one whose element couldn't be found.
export interface TraceRow {
  step: number;
  t: number;
  screen: string;
  key: string;
  label: string;
  action?: string;
  to?: string;
  effect?: Effect;
  explore?: boolean;
  result?: string;
  revealed?: number; // scroll rows: elements newly found below the fold
}

export interface DiffItem {
  status: "changed" | "new" | "missing" | "same";
  base: string | null;
  cand: string | null;
  title: string | null;
  similarity?: number;
  diff?: string;
  changed_ratio?: number;
  bbox?: number[] | null;
}

export interface DiffReport {
  base_run: string;
  cand_run: string;
  base_app: AppInfo;
  cand_app: AppInfo;
  summary: Record<DiffItem["status"], number>;
  items: DiffItem[];
}

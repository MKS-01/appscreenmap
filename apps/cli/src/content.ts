// The commands the terminal home suggests. `c` copies the selected one; `x` runs it here when it needs no editing
// (it has `engine` args or a `shell` line), with its output in runs/.logs/.

export interface Suggestion {
  cmd: string; // what's shown and copied
  what: string;
  engine?: string[]; // run as an engine command
  shell?: string; // run as a shell line (from the current folder)
  env?: Record<string, string>;
}

const PLAYGROUND_CRAWL: Suggestion = {
  cmd: "APP_PASSWORD=playground-demo appscreenmap crawl --apk samples/playground-app/apk/playground-v1.apk --config samples/playground-app/appscreenmap.toml --clear-data",
  what: "map the Playground sample (needs an emulator)",
  engine: ["crawl", "--apk", "samples/playground-app/apk/playground-v1.apk", "--config", "samples/playground-app/appscreenmap.toml", "--clear-data", "--project", "playground", "--name", "playground-v1"],
  env: { APP_PASSWORD: "playground-demo" },
};

const GENERIC_CRAWL: Suggestion[] = [
  { cmd: "appscreenmap crawl --apk path/to/app.apk --clear-data", what: "install an Android build and map it from first launch" },
  { cmd: "appscreenmap crawl --package com.example.app", what: "map an app that's already installed" },
  { cmd: "appscreenmap crawl --platform ios --app path/to/App.app", what: "map an iOS Simulator build (beta)" },
];

const DOCTOR: Suggestion = {
  cmd: "appscreenmap doctor",
  what: "check adb, devices, simulators and the dashboard build",
  engine: ["doctor"],
};

/** Crawl suggestions; in a source checkout the Playground crawl comes first, ready to run. */
export function crawlSuggestions(inCheckout: boolean): Suggestion[] {
  return [...(inCheckout ? [PLAYGROUND_CRAWL] : []), ...GENERIC_CRAWL, DOCTOR];
}

export const AGENT: Suggestion[] = [
  { cmd: "claude", what: "start Claude Code here: the repo's skills teach it every job" },
  { cmd: "/crawl-app", what: "map an app and review the result" },
  { cmd: "/tune-crawler", what: "turn a bad crawl into a test and a fix" },
  { cmd: "/a11y-audit", what: "full WCAG 2.2 audit of the latest run" },
  { cmd: "/security-audit", what: "security audit of an Android build" },
  { cmd: "claude mcp add appscreenmap -- appscreenmap mcp", what: "let any agent session query the maps over MCP" },
];

/** What to run on a finished run, for the Runs tab. */
export function runCommands(runDir: string): Suggestion[] {
  return [
    { cmd: `appscreenmap report ${runDir}`, what: "crawl health: wasted steps, identity issues", engine: ["report", runDir] },
    { cmd: `appscreenmap a11y ${runDir} --report`, what: "WCAG 2.2 checks and the report", engine: ["a11y", runDir, "--report"] },
    { cmd: `appscreenmap perf ${runDir}`, what: "load time per screen, jank", engine: ["perf", runDir] },
  ];
}

export const runnable = (s: Suggestion) => Boolean(s.engine || s.shell);

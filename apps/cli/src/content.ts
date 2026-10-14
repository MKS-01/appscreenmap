// The commands the terminal home suggests. `c` copies the selected one.

export interface Suggestion {
  cmd: string;
  what: string;
}

export const CRAWL: Suggestion[] = [
  { cmd: "appscreenmap crawl --apk path/to/app.apk --clear-data", what: "install an Android build and map it from first launch" },
  { cmd: "appscreenmap crawl --package com.example.app", what: "map an app that's already installed" },
  { cmd: "appscreenmap crawl --platform ios --app path/to/App.app", what: "map an iOS Simulator build (beta)" },
  { cmd: "samples/demo.sh playground", what: "crawl the Playground sample (from a source checkout)" },
  { cmd: "appscreenmap doctor", what: "check adb, devices, simulators and the dashboard build" },
];

export const AGENT: Suggestion[] = [
  { cmd: "claude", what: "start Claude Code here: the repo's skills teach it every job" },
  { cmd: "/crawl-app", what: "map an app and review the result" },
  { cmd: "/tune-crawler", what: "turn a bad crawl into a test and a fix" },
  { cmd: "/a11y-audit", what: "full WCAG 2.2 audit of the latest run" },
  { cmd: "/security-audit", what: "security audit of an Android build" },
  { cmd: "claude mcp add appscreenmap -- appscreenmap mcp", what: "let any agent session query the maps over MCP" },
];

/** What to run on a run, for the Runs tab (`c` copies the first). */
export function runCommands(runDir: string): Suggestion[] {
  return [
    { cmd: `appscreenmap report ${runDir}`, what: "crawl health: wasted steps, identity issues" },
    { cmd: `appscreenmap a11y ${runDir} --report`, what: "WCAG 2.2 checks and the report" },
    { cmd: `appscreenmap perf ${runDir}`, what: "load time per screen, jank" },
  ];
}

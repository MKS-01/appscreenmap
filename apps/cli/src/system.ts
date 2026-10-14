// Small desktop helpers for the terminal home: the clipboard and a new terminal window for an agent session.

function tryRun(cmd: string[], input?: string): boolean {
  try {
    const proc = Bun.spawnSync(cmd, { stdin: input === undefined ? "ignore" : Buffer.from(input), stdout: "ignore", stderr: "ignore" });
    return proc.exitCode === 0;
  } catch {
    return false;
  }
}

/** Copy text to the system clipboard. False when no clipboard tool is available. */
export function copy(text: string): boolean {
  if (process.platform === "darwin") return tryRun(["pbcopy"], text);
  for (const cmd of [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]) {
    if (Bun.which(cmd[0]!) && tryRun(cmd, text)) return true;
  }
  return false;
}

/**
 * Open a new terminal window in `cwd` (macOS Terminal and iTerm2), for starting an agent session next to this one.
 * False elsewhere: the caller copies the command instead.
 */
export function openTerminal(cwd: string, termProgram = process.env.TERM_PROGRAM): boolean {
  if (process.platform !== "darwin") return false;
  const app = termProgram === "iTerm.app" ? "iTerm" : termProgram === "Apple_Terminal" ? "Terminal" : null;
  return app ? tryRun(["open", "-a", app, cwd]) : false;
}

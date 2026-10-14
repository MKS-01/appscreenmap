// Plain console output for the non-interactive commands (setup, update, paths, clean), in the design tokens' colours.
import { createInterface } from "node:readline/promises";
import { C } from "./theme";

const colour = Boolean(process.stdout.isTTY) && !process.env.NO_COLOR;

export function paint(hex: string, s: string): string {
  if (!colour) return s;
  const n = Number.parseInt(hex.slice(1), 16);
  return `\x1b[38;2;${n >> 16};${(n >> 8) & 255};${n & 255}m${s}\x1b[0m`;
}

// Status as a short word in its colour (the design system's rule: never a glyph alone).
const tag = (hex: string, word: string) => `  ${paint(hex, word.padEnd(5))} `;

export const out = {
  title: (s: string) => console.log(paint(C.text, s)),
  ok: (s: string) => console.log(`${tag(C.good, "ok")}${s}`),
  warn: (s: string) => console.log(`${tag(C.warn, "warn")}${s}`),
  bad: (s: string) => console.log(`${tag(C.bad, "fail")}${s}`),
  skip: (s: string) => console.log(`${tag(C.faint, "skip")}${paint(C.dim, s)}`),
  step: (s: string) => console.log(`${tag(C.faint, "")}${paint(C.dim, s)}`),
  dim: (s: string) => console.log(paint(C.dim, s)),
  cmd: (s: string) => paint(C.accent, s),
};

/** Ask a yes/no question; `yes` answers it, and without a terminal the answer is no. */
export async function confirm(question: string, yes = false): Promise<boolean> {
  if (yes) return true;
  if (!process.stdin.isTTY) return false;
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  try {
    return /^y(es)?$/i.test((await rl.question(`  ${question} [y/N] `)).trim());
  } finally {
    rl.close();
  }
}

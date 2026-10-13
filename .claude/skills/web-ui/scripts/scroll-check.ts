// Finds pages that scroll into empty space or clip content sideways. Run after any layout change:
//   bun .claude/skills/web-ui/scripts/scroll-check.ts --base http://127.0.0.1:8795/ [--all]
// For every run in runs/index.json (first 3) and every tab, at 1400 and 390 px, it measures:
//   docOverflow  how far the document is taller than the window. The app scrolls inside `.main`, so anything above 0 means
//                something escaped the scroll container (typically a position:absolute element such as .sr-only whose
//                containing block is outside `.main`) and the page scrolls into empty space below the app.
//   sideways     content wider than the scroll container (it is clipped on phones)
//   emptyTail    empty space after the last element INSIDE a container that really scrolls
// Exit 1 if any page is flagged.
const args = Bun.argv.slice(2);
const opt = (n: string, d: string) => (args.includes(`--${n}`) ? args[args.indexOf(`--${n}`) + 1] : d);
const base = opt("base", "http://127.0.0.1:8765/");
const all = args.includes("--all");
const chrome = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const port = 9300 + Math.floor(Math.random() * 90);
const profile = `${import.meta.dir}/.chrome-scroll-${port}`;
const proc = Bun.spawn([chrome, "--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { stdout: "ignore", stderr: "ignore" });
let flagged = 0;
try {
  const index = await fetch(new URL("runs/index.json", base)).then((r) => r.json());
  const keys: string[] = index.runs.slice(0, 3).map((r: any) => encodeURIComponent(r.path ?? r.id));
  const routes = ["#/", "#/how", "#/design", ...keys.flatMap((k) => ["map", "screens", "replay", "insights", "a11y", "compare"].map((t) => `#/r/${k}/${t}`))];
  let targets: any[] = [];
  for (let i = 0; i < 50 && !targets.length; i++) { await Bun.sleep(150); targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json()).catch(() => []); }
  const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const pending = new Map<number, (v: any) => void>();
  ws.onmessage = (e) => { const m = JSON.parse(String(e.data)); pending.get(m.id)?.(m); };
  const send = (method: string, params: any = {}) => new Promise<any>((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr: string) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true })).result.result.value;
  const probe = `(() => {
    const m = document.querySelector('.main'); if (!m) return null;
    const top = m.getBoundingClientRect().top; let bottom = 0;
    for (const el of m.querySelectorAll('*')) {
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (r.height < 1 || r.width < 1 || cs.visibility === 'hidden' || cs.display === 'none' || cs.position === 'fixed') continue;
      bottom = Math.max(bottom, r.bottom - top + m.scrollTop);
    }
    const scrolls = m.scrollHeight > m.clientHeight + 1;
    return { scrollH: m.scrollHeight, clientH: m.clientHeight, tail: scrolls ? Math.round(m.scrollHeight - bottom) : 0,
             sideways: m.scrollWidth - m.clientWidth, doc: document.documentElement.scrollHeight - innerHeight };
  })()`;
  for (const [w, h] of [[1400, 900], [390, 844]]) {
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: w < 600 });
    for (const r of routes) {
      await send("Page.navigate", { url: "about:blank" }); await Bun.sleep(80);
      await send("Page.navigate", { url: new URL(r, base).toString() }); await Bun.sleep(1700);
      const p = await ev(probe);
      if (!p) { if (all) console.log(`  ${w} ${decodeURIComponent(r)} (no .main)`); continue; }
      const bad = p.doc > 2 || p.sideways > 2 || p.tail > 120;
      if (bad) flagged++;
      if (bad || all) console.log(`${bad ? "✘" : "✔"} ${w} ${decodeURIComponent(r)}  docOverflow=${p.doc} sideways=${p.sideways} emptyTail=${p.tail}`);
    }
  }
  ws.close();
} finally { proc.kill(); await proc.exited; await Bun.$`rm -rf ${profile}`.quiet().nothrow(); }
console.log(flagged ? `${flagged} page(s) flagged` : "No page scrolls into empty space or clips sideways.");
process.exit(flagged ? 1 : 0);

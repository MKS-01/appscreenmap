// Screenshot viewer pages over the Chrome DevTools Protocol, after a real wait.
// (Headless `--screenshot` uses virtual time: CSS animations stay at frame 0, so animated panels look empty.)
//
//   bun .claude/skills/web-ui/scripts/shot.ts --base http://127.0.0.1:8765/ --out <dir> \
//       "#/" "#/how" "#/r/<project>%2F<run-id>/map" [--widths 1400,390] [--themes light,dark] [--reduced-motion] [--wait 1800]
//
// Writes <out>/<slug>-<width>-<theme>.png (full page). Prints each file path.

const args = Bun.argv.slice(2);
const opt = (name: string, def: string) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args.splice(i, 2)[1] : def;
};
const flag = (name: string) => {
  const i = args.indexOf(`--${name}`);
  if (i >= 0) args.splice(i, 1);
  return i >= 0;
};
const base = opt("base", "http://127.0.0.1:8765/");
const out = opt("out", ".");
const widths = opt("widths", "1400,390").split(",").map(Number);
const themes = opt("themes", "light,dark").split(",");
const wait = Number(opt("wait", "1800"));
const reduced = flag("reduced-motion");
const pages = args.length ? args : ["#/"];

const chrome =
  process.env.CHROME ??
  ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"].find((p) =>
    Bun.file(p).size > 0,
  );
if (!chrome) throw new Error("Chrome not found; set CHROME=/path/to/chrome");

const port = 9400 + Math.floor(Math.random() * 400);
const profile = `${out}/.chrome-profile-${port}`;
const proc = Bun.spawn([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], {
  stdout: "ignore",
  stderr: "ignore",
});

try {
  let targets: any[] = [];
  for (let i = 0; i < 50 && !targets.length; i++) {
    await Bun.sleep(150);
    targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json()).catch(() => []);
  }
  const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0;
  const pending = new Map<number, (v: any) => void>();
  ws.onmessage = (e) => {
    const m = JSON.parse(String(e.data));
    pending.get(m.id)?.(m);
  };
  const send = (method: string, params: any = {}) =>
    new Promise<any>((r) => {
      const i = ++id;
      pending.set(i, r);
      ws.send(JSON.stringify({ id: i, method, params }));
    });

  for (const theme of themes) {
    await send("Emulation.setEmulatedMedia", {
      features: [
        { name: "prefers-color-scheme", value: theme },
        { name: "prefers-reduced-motion", value: reduced ? "reduce" : "no-preference" },
      ],
    });
    for (const width of widths) {
      await send("Emulation.setDeviceMetricsOverride", { width, height: width < 600 ? 844 : 1000, deviceScaleFactor: 1, mobile: width < 600 });
      for (const page of pages) {
        await send("Page.navigate", { url: "about:blank" });
        await Bun.sleep(100);
        await send("Page.navigate", { url: new URL(page, base).toString() });
        await Bun.sleep(wait);
        const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
        const slug = page.replace(/^#\/?/, "").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home";
        const file = `${out}/${slug}-${width}-${theme}${reduced ? "-reduced" : ""}.png`;
        await Bun.write(file, Buffer.from(shot.result.data, "base64"));
        console.log(file);
      }
    }
  }
  ws.close();
} finally {
  proc.kill();
  await proc.exited;
  await Bun.$`rm -rf ${profile}`.quiet().nothrow();
}

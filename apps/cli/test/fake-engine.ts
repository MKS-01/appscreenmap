// Stands in for `appscreenmap-engine` in tests: `--version`, and `serve` answering /runs/index.json like the real one.
const args = process.argv.slice(2);
if (args[0] === "--version") {
  console.log("appscreenmap 9.9.9");
  process.exit(0);
}
if (args[0] === "serve") {
  if (process.env.FAKE_ENGINE_FAIL) {
    console.error("Web viewer not built. Run: bun install && make viewer");
    process.exit(2);
  }
  const port = Number(args[args.indexOf("--port") + 1]);
  Bun.serve({
    hostname: "127.0.0.1",
    port,
    fetch: (req) =>
      new URL(req.url).pathname === "/runs/index.json" ? Response.json({ runs: [] }) : new Response("viewer"),
  });
}

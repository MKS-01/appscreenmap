import fs from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// In dev, serve the crawler's output directory at /runs (same URL layout as `appscreenmap serve`).
const runsRoot = path.resolve(__dirname, process.env.APPSCREENMAP_RUNS ?? "../runs");

const TYPES: Record<string, string> = {
  ".json": "application/json",
  ".jsonl": "application/x-ndjson",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".xml": "text/xml; charset=utf-8",
  ".yaml": "text/yaml; charset=utf-8",
  ".mmd": "text/plain; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

// Mirrors `PUT /runs/<run>/notes.json` in `appscreenmap serve` (src/appscreenmap/notes.py).
// Runs live at runs/<project>/<run-id>/ (or legacy runs/<run-id>/).
const NOTES_RE = /^\/((?:[A-Za-z0-9][A-Za-z0-9_.-]*\/)?[A-Za-z0-9][A-Za-z0-9_.-]*)\/notes\.json$/;
const MAX_NOTES_BYTES = 1_000_000;

function saveNotes(req: IncomingMessage, res: ServerResponse) {
  const m = NOTES_RE.exec((req.url ?? "").split("?")[0]);
  const runDir = m && !m[1].includes("..") ? path.join(runsRoot, ...m[1].split("/")) : null;
  const fail = (code: number, msg: string) => {
    res.statusCode = code;
    res.end(msg);
  };
  if (!runDir || !fs.existsSync(path.join(runDir, "map.json"))) return fail(404, "not found");
  if (!(req.headers["content-type"] ?? "").startsWith("application/json")) return fail(415, "expected JSON");
  const chunks: Buffer[] = [];
  let size = 0;
  req.on("data", (c: Buffer) => {
    size += c.length;
    if (size <= MAX_NOTES_BYTES) chunks.push(c);
  });
  req.on("end", () => {
    if (size > MAX_NOTES_BYTES) return fail(413, "too large");
    let doc: { appscreenmap_notes?: number; notes?: unknown };
    try {
      doc = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
      return fail(400, "invalid JSON");
    }
    if (doc?.appscreenmap_notes !== 1 || !doc.notes || typeof doc.notes !== "object" || Array.isArray(doc.notes))
      return fail(400, "not an AppScreenMap notes document");
    const out = path.join(runDir, "notes.json");
    const tmp = `${out}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ ...doc, run: path.basename(runDir) }, null, 1));
    fs.renameSync(tmp, out);
    res.statusCode = 204;
    res.end();
  });
}

function serveRuns(): Plugin {
  return {
    name: "appscreenmap-runs",
    configureServer(server) {
      server.middlewares.use("/runs", (req, res, next) => {
        if (req.method === "PUT") return saveNotes(req, res);
        const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
        const file = path.resolve(runsRoot, "." + rel);
        if (!file.startsWith(runsRoot + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
          res.statusCode = 404;
          return res.end("not found");
        }
        res.setHeader("Content-Type", TYPES[path.extname(file)] ?? "application/octet-stream");
        res.setHeader("Cache-Control", "no-store");
        fs.createReadStream(file).pipe(res);
        void next;
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveRuns()],
  server: { port: 5173 },
});

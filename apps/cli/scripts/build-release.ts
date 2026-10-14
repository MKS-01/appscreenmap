// Build a release folder: what a GitHub Release will hold, and what `setup`, `update` and install.sh read.
//   bun apps/cli/scripts/build-release.ts [out-dir]     (make release-local → dist/release/)
// Test against it with APPSCREENMAP_RELEASE_URL=file://<out-dir>/. Nothing is published: no releases until asked.
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { MAP_SCHEMA_VERSION } from "../src/schema";

const ROOT = resolve(import.meta.dir, "..", "..", "..");
const OUT = resolve(process.argv[2] ?? join(ROOT, "dist", "release"));
const TARGETS = ["darwin-arm64", "darwin-x64"] as const; // macOS first

function run(cmd: string[], cwd = ROOT) {
  const p = Bun.spawnSync(cmd, { cwd, stdout: "inherit", stderr: "inherit" });
  if (p.exitCode !== 0) throw new Error(`failed: ${cmd.join(" ")}`);
}
const sha = (file: string) => new Bun.CryptoHasher("sha256").update(readFileSync(file)).digest("hex");
const ref = (file: string) => ({ file, sha256: sha(join(OUT, file)) });

const cliVersion = JSON.parse(readFileSync(join(ROOT, "apps/cli/package.json"), "utf8")).version as string;
const viewerVersion = JSON.parse(readFileSync(join(ROOT, "apps/viewer/package.json"), "utf8")).version as string;
const engineVersion = readFileSync(join(ROOT, "apps/engine/pyproject.toml"), "utf8").match(/^version = "([^"]+)"/m)![1]!;

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

console.log("▸ engine wheels");
run(["uv", "build", "--all-packages", "--wheel", "--out-dir", OUT]);
for (const f of readdirSync(OUT)) if (f.startsWith("appscreenmap_testkit-") || !f.endsWith(".whl")) rmSync(join(OUT, f), { force: true });
const wheels = readdirSync(OUT).filter((f) => f.endsWith(".whl")).sort();

console.log("▸ dashboard");
run(["bun", "run", "build"], join(ROOT, "apps/viewer"));
const stage = join(OUT, ".viewer");
cpSync(join(ROOT, "apps/viewer/dist"), stage, { recursive: true });
writeFileSync(join(stage, "viewer.json"), JSON.stringify({ version: viewerVersion, map_schema: MAP_SCHEMA_VERSION, min_cli: cliVersion }, null, 1) + "\n");
const viewerFile = `viewer-${viewerVersion}.tar.gz`;
run(["tar", "-czf", join(OUT, viewerFile), "-C", stage, "."]);
rmSync(stage, { recursive: true, force: true });

console.log("▸ cli binaries");
const binaries: Record<string, { file: string; sha256: string }> = {};
for (const t of TARGETS) {
  const file = `appscreenmap-${t}`;
  run(["bun", "build", "./src/index.tsx", "--compile", `--target=bun-${t}`, "--outfile", join(OUT, file)], join(ROOT, "apps/cli"));
  binaries[t] = ref(file);
}
cpSync(join(ROOT, "install.sh"), join(OUT, "install.sh"));

const manifest = {
  version: cliVersion,
  map_schema: MAP_SCHEMA_VERSION,
  cli: { version: cliVersion, binaries },
  engine: { version: engineVersion, wheels: wheels.map(ref) },
  viewer: { ...ref(viewerFile), version: viewerVersion, map_schema: MAP_SCHEMA_VERSION, min_cli: cliVersion },
};
writeFileSync(join(OUT, "manifest.json"), JSON.stringify(manifest, null, 1) + "\n");
const files = readdirSync(OUT).filter((f) => f !== "SHA256SUMS" && !f.startsWith(".")).sort();
writeFileSync(join(OUT, "SHA256SUMS"), files.map((f) => `${sha(join(OUT, f))}  ${f}`).join("\n") + "\n");
console.log(`✓ release ${cliVersion} in ${OUT}  (${files.length} files)\n  APPSCREENMAP_RELEASE_URL=file://${OUT}/`);
if (!existsSync(join(OUT, "manifest.json"))) process.exit(1);

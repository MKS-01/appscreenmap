import { href } from "../router";
import type { AppMapData } from "../types";
import { CopyButton } from "./common";
import { Icon } from "./Icon";

// A canvas made by a stack scan before any crawl: no screens yet. Says what's next instead of an empty map.

export default function EmptyCanvas({ run, map }: { run: string; map: AppMapData }) {
  const app = map.run.app;
  const name = app.label ?? app.package;
  const prompt = `Map ${name} (${app.package}) on the emulator into its canvas`;
  const cmd = `appscreenmap crawl --package ${app.package} --max-steps 200`;
  const merge = `appscreenmap merge --into runs/${run} runs/<new-run> --labels "First crawl" --move`;
  return (
    <div className="page empty-canvas">
      <span className="ins-kicker">No screens yet</span>
      <h1>Map the screens of {name}</h1>
      <p className="muted">
        This canvas was made from a scan of the build on the emulator. A crawl adds its screens here, as its first scenario.{" "}
        <a href={href("r", run, "insights", "stack")}>See what it's built with →</a>
      </p>
      <div className="start-grid">
        <div className="panel start-step">
          <span className="start-n">
            <Icon name="bot" size={14} />
          </span>
          <b>Ask your agent</b>
          <span className="small muted">It crawls the app, reviews the map and merges the run into this canvas.</span>
          <div className="row" style={{ gap: 6, marginTop: "auto" }}>
            <code className="grow ellipsis start-cmd is-prompt" title={prompt}>
              {prompt}
            </code>
            <CopyButton text={prompt} />
          </div>
        </div>
        <div className="panel start-step">
          <span className="start-n">
            <Icon name="terminal" size={14} />
          </span>
          <b>Or crawl from a terminal</b>
          <span className="small muted">Then add the new run to this canvas.</span>
          <div className="row" style={{ gap: 6 }}>
            <code className="grow ellipsis start-cmd" title={cmd}>
              {cmd}
            </code>
            <CopyButton text={cmd} />
          </div>
          <div className="row" style={{ gap: 6 }}>
            <code className="grow ellipsis start-cmd" title={merge}>
              {merge}
            </code>
            <CopyButton text={merge} />
          </div>
        </div>
      </div>
    </div>
  );
}

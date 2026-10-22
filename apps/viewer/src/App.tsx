import { useEffect, useState } from "react";
import { useLive, type Live } from "./activity";
import { runKey, useIndex, useMap } from "./api";
import { useCaptures } from "./captures";
import { ActivityDock, LiveChip } from "./components/Activity";
import { ErrorBox, Loading, Logo, StatusBadge } from "./components/common";
import { PlatformCtx, platformOf } from "./a11y";
import { href, useRoute, type Route } from "./router";
import { useStored } from "./storage";
import A11y from "./views/A11y";
import Compare from "./views/Compare";
import DesignSystem from "./views/DesignSystem";
import HowItWorks from "./views/HowItWorks";
import Insights from "./views/Insights";
import Logs from "./views/Logs";
import MapView from "./views/MapView";
import Network from "./views/Network";
import Replay from "./views/Replay";
import Runs from "./views/Runs";
import ScreenDetail from "./views/ScreenDetail";
import Screens from "./views/Screens";

/** What the top bar needs to show the live chip and the Logs link. */
interface Activity {
  live: Live | null;
  dock: boolean;
  toggleDock: () => void;
}

export default function App() {
  const route = useRoute();
  const { live } = useLive();
  const [dock, setDock] = useStored("activity.dock", false);
  // The drawer shows only around a running command: it appears with one (if it was left open) and stays until
  // closed, so a finished run's last lines don't vanish under you. With nothing running, it stays hidden.
  const active = !!(live?.running.length || live?.recent.length);
  const [held, setHeld] = useState(false);
  useEffect(() => {
    if (dock && active) setHeld(true);
  }, [dock, active]);
  const activity: Activity = { live, dock: dock && (active || held), toggleDock: () => (setDock(!activity.dock), setHeld(!activity.dock)) };
  const page = route.page === "how" ? <HowItWorks /> : route.page === "design" ? <DesignSystem /> : route.page === "logs" ? <Logs query={route.query} /> : <Runs />;
  return (
    <div className="app">
      {route.page === "run" ? (
        <RunShell route={route} activity={activity} />
      ) : (
        <>
          <TopBar route={route} activity={activity} />
          <div className="main">{page}</div>
        </>
      )}
      {activity.dock && live && route.page !== "logs" && <ActivityDock live={live} onClose={() => (setDock(false), setHeld(false))} />}
    </div>
  );
}

function TopBar({ route, activity, children }: { route: Route; activity: Activity; children?: React.ReactNode }) {
  return (
    <header className="topbar">
      <a className="brand" href="#/">
        <Logo /> <span className="brand-name">AppScreenMap</span>
      </a>
      {children}
      <div className="spacer" />
      <LiveChip live={activity.live} open={activity.dock} onToggle={activity.toggleDock} />
      <a className={`toplink ${route.page === "runs" ? "active" : ""}`} href="#/">
        Runs
      </a>
      {activity.live?.has_logs && (
        <a className={`toplink logs ${route.page === "logs" ? "active" : ""}`} href="#/logs">
          Logs
        </a>
      )}
      <a className={`toplink how ${route.page === "how" ? "active" : ""}`} href="#/how">
        How it works
      </a>
    </header>
  );
}

function RunShell({ route, activity }: { route: Route; activity: Activity }) {
  const run = route.run!;
  const { data, error } = useMap(run);
  const { data: index } = useIndex();
  const [reloadN, setReloadN] = useState(0);
  const { data: caps } = useCaptures(run, reloadN);
  const reload = () => setReloadN((n) => n + 1);

  // Old links address a run by bare id (runs/<id>/); runs now live at runs/<project>/<id>/. Redirect.
  useEffect(() => {
    const row = index?.runs.find((r) => r.id === run && runKey(r) !== run);
    if (row) location.replace(location.hash.replace(`#/r/${encodeURIComponent(run)}`, `#/r/${encodeURIComponent(runKey(row))}`));
  }, [index, run]);
  const tab = route.tab === "s" ? "screens" : route.tab!;
  const app = data?.run.app;
  const tabs: [string, string, number | undefined][] = [
    ["map", "Map", data?.stats.transitions],
    ["screens", "Screens", data?.stats.screens],
    ["replay", "Crawl replay", data?.run.steps],
    ["insights", "Insights", undefined],
    ["a11y", "Accessibility", undefined],
    ["compare", "Compare", undefined],
    // Only with `serve`: it lists the captures and starts manual sessions. One click from any run page.
    ...(caps ? ([["network", "Network · Logs", (caps.network?.events ?? 0) + (caps.logs?.lines ?? 0) || undefined]] as [string, string, number | undefined][]) : []),
  ];

  let body: React.ReactNode = <Loading />;
  if (error) body = <ErrorBox error={error} />;
  else if (data) {
    if (route.tab === "s" && route.arg) body = <ScreenDetail run={run} map={data} sid={route.arg} caps={caps} />;
    else if (tab === "network" && caps) body = <Network run={run} map={data} caps={caps} reload={reload} />;
    else if (tab === "screens") body = <Screens run={run} map={data} />;
    else if (tab === "replay") body = <Replay run={run} map={data} caps={caps} />;
    else if (tab === "insights") body = <Insights run={run} map={data} audit={route.arg} />;
    else if (tab === "a11y") body = <A11y run={run} map={data} view={route.arg} />;
    else if (tab === "compare") body = <Compare run={run} map={data} base={route.arg} />;
    else body = <MapView run={run} map={data} focus={route.query.get("focus") ?? undefined} layout={route.query.get("layout") ?? undefined} />;
  }

  return (
    <>
      <TopBar route={route} activity={activity}>
        <span className="crumb">
          <span className="faint">/</span>
          <b>{app?.label ?? run}</b>
          {app?.version && <span className="faint">v{app.version}</span>}
          {data && <StatusBadge status={data.run.status} />}
          {data && activity.live?.has_logs && (
            <a className="crumb-link small" href={`#/logs?run=${encodeURIComponent(data.run.id)}`}>
              Log
            </a>
          )}
        </span>
      </TopBar>
      <nav className="tabs">
        {tabs.map(([id, label, n]) => (
          <a key={id} className={`tab ${tab === id ? "active" : ""}`} href={href("r", run, id)}>
            {label}
            {n != null && <span className="count">{n}</span>}
          </a>
        ))}
      </nav>
      <div className="main" style={tab === "map" && route.tab !== "s" ? { overflow: "hidden" } : undefined}>
        <PlatformCtx.Provider value={data ? platformOf(data) : "android"}>{body}</PlatformCtx.Provider>
      </div>
    </>
  );
}

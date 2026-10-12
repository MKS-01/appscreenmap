import { useEffect } from "react";
import { runKey, useIndex, useMap } from "./api";
import { ErrorBox, Loading, Logo, StatusBadge } from "./components/common";
import { href, useRoute, type Route } from "./router";
import A11y from "./views/A11y";
import Compare from "./views/Compare";
import DesignSystem from "./views/DesignSystem";
import HowItWorks from "./views/HowItWorks";
import Insights from "./views/Insights";
import MapView from "./views/MapView";
import Replay from "./views/Replay";
import Runs from "./views/Runs";
import ScreenDetail from "./views/ScreenDetail";
import Screens from "./views/Screens";

export default function App() {
  const route = useRoute();
  return (
    <div className="app">
      {route.page === "run" ? (
        <RunShell route={route} />
      ) : (
        <>
          <TopBar route={route} />
          <div className="main">{route.page === "how" ? <HowItWorks /> : route.page === "design" ? <DesignSystem /> : <Runs />}</div>
        </>
      )}
    </div>
  );
}

function TopBar({ route, children }: { route: Route; children?: React.ReactNode }) {
  return (
    <header className="topbar">
      <a className="brand" href="#/">
        <Logo /> <span className="brand-name">AppScreenMap</span>
      </a>
      {children}
      <div className="spacer" />
      <a className={`toplink ${route.page === "runs" ? "active" : ""}`} href="#/">
        Runs
      </a>
      <a className={`toplink how ${route.page === "how" ? "active" : ""}`} href="#/how">
        How it works
      </a>
    </header>
  );
}

function RunShell({ route }: { route: Route }) {
  const run = route.run!;
  const { data, error } = useMap(run);
  const { data: index } = useIndex();

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
  ];

  let body: React.ReactNode = <Loading />;
  if (error) body = <ErrorBox error={error} />;
  else if (data) {
    if (route.tab === "s" && route.arg) body = <ScreenDetail run={run} map={data} sid={route.arg} />;
    else if (tab === "screens") body = <Screens run={run} map={data} />;
    else if (tab === "replay") body = <Replay run={run} map={data} />;
    else if (tab === "insights") body = <Insights run={run} map={data} />;
    else if (tab === "a11y") body = <A11y run={run} map={data} view={route.arg} />;
    else if (tab === "compare") body = <Compare run={run} map={data} base={route.arg} />;
    else body = <MapView run={run} map={data} focus={route.query.get("focus") ?? undefined} layout={route.query.get("layout") ?? undefined} />;
  }

  return (
    <>
      <TopBar route={route}>
        <span className="crumb">
          <span className="faint">/</span>
          <b>{app?.label ?? run}</b>
          {app?.version && <span className="faint">v{app.version}</span>}
          {data && <StatusBadge status={data.run.status} />}
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
        {body}
      </div>
    </>
  );
}

import { useEffect, useState } from "react";

// Hash routes so the viewer works from any static host and from `appscreenmap serve`.
//   #/                         runs
//   #/how                      how it works
//   #/design                   design system reference (not in the nav)
//   #/r/<run>/<tab>            map | screens | replay | insights | compare
//   #/r/<run>/s/<screen>       screen detail
//   #/r/<run>/compare/<base>   compare against a baseline run
//   #/r/<run>/insights/<audit> one audit (coverage, a11y, perf, adaptive, store, platform, security, …)

export interface Route {
  page: "runs" | "how" | "design" | "run";
  run?: string;
  tab?: string;
  arg?: string;
  query: URLSearchParams;
}

export function parseHash(hash: string): Route {
  const [path, qs = ""] = hash.replace(/^#/, "").split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const query = new URLSearchParams(qs);
  if (parts[0] === "how") return { page: "how", query };
  if (parts[0] === "design") return { page: "design", query };
  if (parts[0] === "r" && parts[1]) return { page: "run", run: parts[1], tab: parts[2] ?? "map", arg: parts[3], query };
  return { page: "runs", query };
}

export const href = (...parts: (string | undefined)[]) =>
  "#/" + parts.filter((p): p is string => !!p).map(encodeURIComponent).join("/");

export const screenHref = (run: string, sid: string) => href("r", run, "s", sid);

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (h: string) => {
  location.hash = h;
};

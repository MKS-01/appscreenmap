import { densityFor } from "../a11y";
import { shortActivity } from "../util";
import { statusFromScore, type BuildContext } from "./builtin";
import { refs } from "./sources";
import type { AuditFinding, AuditReport } from "./types";

// Placeholder reports for audits whose data source doesn't exist yet, so the Insights UI can be designed and
// tested end to end. Every one is marked `source: "sample"` (or `sample: true` per finding) and the viewer labels
// it. Platform facts and dates come from the official pages in sources.ts; the per-app findings are invented.
// Replace each builder with a real one (or have the crawler write audits/<id>.json) as the audit ships.

// ── adaptive UI: real device + manifest facts, sample layout checks ──────────

type SizeClass = "compact" | "medium" | "expanded";
const sizeClass = (dp: number): SizeClass => (dp < 600 ? "compact" : dp < 840 ? "medium" : "expanded");

export function adaptiveReport({ map }: BuildContext): AuditReport {
  const { scale } = densityFor(map);
  const display = map.run.device.display;
  const widthDp = display?.width_dp ?? Math.round((map.run.device.width || 1080) / scale);
  const tested = display?.window_class ?? sizeClass(widthDp);
  const locked = Object.entries(map.run.app.orientation_locked ?? {});

  const real: AuditFinding[] = locked.map(([activity, orientation]) => ({
    id: `orientation::${activity}`,
    severity: "error",
    category: "Large screens",
    platform: "android",
    title: `${shortActivity(activity)} is locked to ${orientation}`,
    detail:
      "Apps targeting Android 17 (API 37) can no longer opt out: on large screens (sw ≥ 600 dp) the system ignores orientation, resizability and aspect-ratio restrictions. It also fails WCAG 1.3.4 Orientation unless the lock is essential.",
    fix: "Remove screenOrientation from the manifest and support both orientations; test at medium and expanded widths.",
    refs: refs("android17LargeScreens", "wcagOrientation"),
  }));

  const sample: AuditFinding[] = [
    {
      id: "sample::stretched",
      severity: "warning",
      category: "Expanded width",
      platform: "android",
      screen: map.screens.find((s) => s.kind === "app" && s.patterns.includes("list"))?.id,
      title: "List stretches edge to edge at expanded width",
      detail: "At 1280 dp the rows span the whole window. Long lines are hard to scan and touch targets drift far apart.",
      fix: "Cap content width, or switch to a list-detail layout at the expanded size class.",
      refs: refs("windowSizeClasses"),
      sample: true,
    },
    {
      id: "sample::nav-rail",
      severity: "warning",
      category: "Navigation",
      platform: "android",
      screen: map.screens.find((s) => s.kind === "app" && s.patterns.includes("bottom_nav"))?.id,
      title: "Bottom navigation kept at medium and expanded widths",
      detail: "Android's adaptive guidance swaps a bottom bar for a navigation rail once the window isn't compact.",
      fix: "Use NavigationSuiteScaffold, which picks bar, rail or drawer from the window size class.",
      refs: refs("windowSizeClasses"),
      sample: true,
    },
    {
      id: "sample::ime-rotation",
      severity: "info",
      category: "Configuration changes",
      platform: "android",
      title: "Keyboard closes after rotating a form",
      detail: "Android 17 no longer restores IME visibility after an unhandled configuration change, so a focused field loses its keyboard on rotate.",
      fix: "Request the IME explicitly after recreation, or handle the configuration change.",
      refs: refs("android17All"),
      sample: true,
    },
    {
      id: "sample::iphone-duo",
      severity: "info",
      category: "New devices",
      platform: "ios",
      title: "iPhone Duo poses not checked yet",
      detail: "iPhone Duo ships Oct 23, 2026. Apple asks apps to recompile with Xcode 27.1 and check every pose and orientation in Device Hub.",
      fix: "Recompile with Xcode 27.1 and review each pose; an iOS crawl will cover this once the simulator driver lands.",
      refs: refs("appleIphoneDuo", "appleIphoneDuoPrepare"),
      sample: true,
    },
  ];

  const findings = [...real, ...sample];
  const score = Math.max(0, 100 - 20 * real.length - 8 * sample.filter((f) => f.severity === "warning").length);
  return {
    schema: 1,
    audit: "adaptive",
    title: "Adaptive UI",
    source: "mixed",
    status: statusFromScore(score),
    score,
    score_note: "100, minus 20 per orientation or resizability lock and 8 per layout warning. Layout checks are sample data until multi-size crawls exist.",
    summary: `Crawled at ${widthDp} dp wide (${tested}). ${locked.length ? `${locked.length} orientation lock${locked.length === 1 ? "" : "s"} found in the manifest.` : "No orientation locks in the manifest."}`,
    metrics: [
      { label: "crawl width", value: widthDp, unit: "dp", hint: `${tested} window size class` },
      { label: "size classes tested", value: "1 of 3", tone: "warn", hint: `${tested} only` },
      { label: "orientation locks", value: locked.length, tone: locked.length ? "bad" : "good" },
      { label: "layout warnings", value: sample.filter((f) => f.severity === "warning").length, tone: "warn", hint: "sample data", sample: true },
    ],
    charts: [
      {
        type: "columns",
        title: "Layout issues by window size class",
        note: "Needs crawls at 600 and 840 dp",
        sample: true,
        data: [
          { label: "compact", value: real.length },
          { label: "medium", value: real.length + 1 },
          { label: "expanded", value: real.length + 2 },
        ],
      },
    ],
    findings,
    refs: refs("android17LargeScreens", "windowSizeClasses", "appleIphoneDuoPrepare", "wcagOrientation"),
  };
}

// ── store readiness: Google Play + App Store requirements with dates ─────────

export function storeReport({ map }: BuildContext): AuditReport {
  const pkg = map.run.app.package;
  const findings: AuditFinding[] = [
    {
      id: "play::target-36",
      severity: "error",
      category: "Target API level",
      platform: "android",
      title: "App updates must target Android 16 (API 36)",
      detail: `Since Aug 31, 2026, new apps and app updates on Google Play must target API 36 or higher. ${pkg} targets API 35 (sample value: target SDK isn't read from the APK yet). Extensions run to Nov 1, 2026.`,
      fix: "Raise targetSdk to 36, then work through the Android 16 behavior changes for apps targeting 36.",
      due: "2026-11-01",
      refs: refs("playTargetSdk", "playTargetSdkHelp"),
    },
    {
      id: "play::existing-35",
      severity: "info",
      category: "Target API level",
      platform: "android",
      title: "Existing apps: API 35 keeps the app visible to new users",
      detail: "Since Aug 31, 2026, apps targeting API 34 or lower are hidden from new users on devices running a newer Android version than the app targets.",
      due: "2026-08-31",
      refs: refs("playTargetSdk"),
    },
    {
      id: "play::target-37",
      severity: "info",
      category: "Target API level",
      platform: "android",
      title: "Next: Android 17 (API 37)",
      detail: "Google Play usually requires the newest API level for updates one year after its release. Plan for the API 37 behavior changes now (see Platform changes).",
      refs: refs("android17"),
    },
    {
      id: "appstore::sdk-26",
      severity: "info",
      category: "Build SDK",
      platform: "ios",
      title: "Uploads must be built with Xcode 26 and a 26 SDK",
      detail: "Since Apr 28, 2026, App Store Connect only accepts builds made with Xcode 26 or later against the iOS/iPadOS 26 SDKs.",
      due: "2026-04-28",
      refs: refs("appleUpcoming"),
    },
    {
      id: "appstore::iphone-duo-screens",
      severity: "warning",
      category: "Product page",
      platform: "ios",
      title: "iPhone Duo screenshots required from April 2027",
      detail: "Apps and games submitted from April 2027 must include iPhone Duo screenshots. New screenshot and preview specs are in App Store Connect.",
      fix: "Capture iPhone Duo screenshots in each orientation; AppScreenMap's crawl screenshots can seed them once the iOS driver lands.",
      due: "2027-04-01",
      refs: refs("appleIphoneDuo", "appleScreenshotSpecs"),
    },
  ];
  return {
    schema: 1,
    audit: "store",
    title: "Store readiness",
    tool: "sample",
    source: "sample",
    status: "fail",
    score: 58,
    score_note: "Sample score until the APK's target SDK and the store listing are read.",
    summary: "Google Play target API and App Store build and screenshot requirements, with their deadlines.",
    metrics: [
      { label: "target SDK", value: 35, tone: "bad", hint: "sample: Play requires 36 for updates" },
      { label: "min SDK", value: 26, hint: "sample" },
      { label: "next deadline", value: "Nov 1, 2026", tone: "warn", hint: "Play target API extension ends" },
      { label: "open requirements", value: findings.filter((f) => f.severity !== "info").length, tone: "bad" },
    ],
    charts: [],
    findings,
    refs: refs("playTargetSdk", "playTargetSdkHelp", "appleUpcoming", "appleIphoneDuo"),
  };
}

// ── platform changes: this year's Android / iOS release vs. the app ─────────

export function platformReport(): AuditReport {
  const t37 = "Targets API 37";
  const all = "All apps on Android 17";
  const f = (id: string, severity: AuditFinding["severity"], category: string, title: string, detail: string, fix?: string, ...ids: Parameters<typeof refs>): AuditFinding => ({
    id,
    severity,
    category,
    platform: "android",
    title,
    detail,
    fix,
    refs: refs(...ids),
  });
  const findings: AuditFinding[] = [
    f("a17::large-screens", "error", t37, "Orientation and resizability ignored on large screens", "Affected: the manifest locks an activity's orientation. At API 37 the Android 16 opt-out is gone.", "Support every orientation and window size; see Adaptive UI.", "android17LargeScreens"),
    f("a17::local-network", "warning", t37, "Local network access needs ACCESS_LOCAL_NETWORK", "Check: the app opens LAN sockets (sample signal from a planned jadx scan).", "Request the runtime permission, or use a system device picker.", "android17", "localNetwork"),
    f("a17::ct", "info", t37, "Certificate Transparency on by default", "Check: connections to servers with certificates missing from CT logs will fail.", undefined, "android17", "securityConfig"),
    f("a17::ech", "info", t37, "Encrypted Client Hello enabled", "No action unless the network security config needs <domainEncryption> tuning.", undefined, "android17", "securityConfig"),
    f("a17::sms-otp", "info", t37, "SMS OTPs delayed three hours for other apps", "Not affected: the app doesn't read SMS (sample).", "Use SMS Retriever or SMS User Consent.", "android17"),
    f("a17::static-final", "warning", t37, "Reflection can't change static final fields", "Check: needs a jadx scan for Field.set on final fields (planned).", undefined, "android17"),
    f("a17::bg-audio", "info", all, "Background audio hardening", "Audio playback, focus and volume calls outside a valid lifecycle fail silently.", undefined, "android17All"),
    f("a17::memory", "info", all, "App memory limits based on device RAM", "Leaky or outlier apps can be killed; compare with the Performance audit.", undefined, "android17All"),
    f("a17::cleartext", "warning", all, "usesCleartextTraffic will be deprecated", "Affected: the manifest sets usesCleartextTraffic (sample). Move to a network security config file.", undefined, "android17All", "securityConfig"),
    f("a17::ime-rotation", "info", all, "Keyboard visibility isn't restored after rotation", "Forms that rely on it must request the IME again; see Adaptive UI.", undefined, "android17All"),
    {
      id: "ios::iphone-duo",
      severity: "info",
      category: "iOS 27 · new devices",
      platform: "ios",
      title: "iPhone Duo: recompile with Xcode 27.1",
      detail: "Available Oct 23, 2026. Check every pose and orientation in Device Hub.",
      due: "2026-10-23",
      refs: refs("appleIphoneDuo", "appleIphoneDuoPrepare"),
    },
  ];
  return {
    schema: 1,
    audit: "platform",
    title: "Platform changes",
    tool: "sample",
    source: "sample",
    status: "warn",
    score: 72,
    score_note: "Sample score: share of this year's behavior changes that don't affect the app or are already handled.",
    summary: "Android 17 behavior changes and this year's iOS device changes, checked against what the app uses.",
    metrics: [
      { label: "changes tracked", value: findings.length },
      { label: "affect the app", value: findings.filter((x) => x.severity === "error").length, tone: "bad" },
      { label: "need a check", value: findings.filter((x) => x.severity === "warning").length, tone: "warn" },
      { label: "FYI", value: findings.filter((x) => x.severity === "info").length },
    ],
    charts: [],
    findings,
    refs: refs("android17", "android17All", "appleIphoneDuo"),
  };
}

// ── security: planned static (jadx) + dynamic (frida) scan ───────────────────

export function securityReport({ map }: BuildContext): AuditReport {
  const pkg = map.run.app.package;
  const s = (id: string, severity: AuditFinding["severity"], category: string, title: string, detail: string, fix: string): AuditFinding => ({
    id,
    severity,
    category,
    platform: "android",
    title,
    detail,
    fix,
  });
  const findings: AuditFinding[] = [
    s("sec::secret", "error", "Static (jadx)", "Hard-coded API key in BuildConfig", `A string matching an API key pattern ships in ${pkg}'s dex.`, "Move secrets server-side or into an encrypted config fetched at runtime."),
    s("sec::cleartext", "warning", "Manifest", "Cleartext traffic allowed app-wide", "android:usesCleartextTraffic=\"true\". Android 17 starts deprecating this attribute.", "Remove it; allow cleartext per domain in a network security config if you must."),
    s("sec::exported", "warning", "Manifest", "Exported activity without a permission", `${shortActivity(map.run.app.activities?.[1] ?? "SettingsActivity")} is exported and has no android:permission.`, "Set exported=\"false\", or protect it with a signature permission."),
    s("sec::backup", "warning", "Manifest", "allowBackup enabled", "App data can be copied with adb backup or a cloud restore.", "Set allowBackup=\"false\" or add dataExtractionRules that exclude tokens."),
    s("sec::pinning", "info", "Dynamic (frida)", "No certificate pinning observed", "TLS connections accepted a user-installed CA during the instrumented run.", "Pin public keys for your own API hosts via the network security config."),
    s("sec::webview-js", "info", "Static (jadx)", "WebView with JavaScript and a JS interface", "addJavascriptInterface on a WebView that loads remote URLs.", "Load only trusted origins, or drop the interface."),
  ];
  return {
    schema: 1,
    audit: "security",
    title: "Security",
    tool: "jadx + frida (planned)",
    source: "sample",
    status: "fail",
    score: 61,
    score_note: "Sample score: 100 minus 20 per error, 8 per warning, 2 per info.",
    summary: "Static decompile checks (jadx), manifest review and dynamic instrumentation (frida). Not built yet; the findings below are illustrative.",
    metrics: [
      { label: "critical", value: 1, tone: "bad" },
      { label: "warnings", value: 3, tone: "warn" },
      { label: "exported components", value: 2, hint: "sample" },
      { label: "debuggable", value: "no", tone: "good", hint: "sample" },
    ],
    charts: [
      {
        type: "bars",
        title: "Findings by check",
        data: [
          { label: "Manifest", value: 3, tone: "warn" },
          { label: "Static (jadx)", value: 2, tone: "bad" },
          { label: "Dynamic (frida)", value: 1 },
        ],
      },
    ],
    findings,
    refs: refs("securityConfig", "android17All"),
  };
}


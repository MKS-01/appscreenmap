import type { AuditRef } from "./types";

// Official platform and store sources that Insights checks follow. One catalog, so a yearly platform release or a
// new store deadline is a change here, not a hunt through audits. `date` = when the entry was last checked against
// the source. Keep entries to Android Developers, Google Play, Apple Developer and W3C pages.

const CHECKED = "2026-10-13";

export const SOURCES = {
  android17: {
    title: "Android 17 behavior changes: apps targeting Android 17",
    url: "https://developer.android.com/about/versions/17/behavior-changes-17",
    publisher: "Android Developers",
    date: CHECKED,
  },
  android17All: {
    title: "Android 17 behavior changes: all apps",
    url: "https://developer.android.com/about/versions/17/behavior-changes-all",
    publisher: "Android Developers",
    date: CHECKED,
  },
  android17LargeScreens: {
    title: "Android 17: orientation, resizability and aspect ratio ignored on large screens",
    url: "https://developer.android.com/about/versions/17/changes/ff-restrictions-ignored",
    publisher: "Android Developers",
    date: CHECKED,
  },
  localNetwork: {
    title: "Local network permission",
    url: "https://developer.android.com/privacy-and-security/local-network-permission",
    publisher: "Android Developers",
    date: CHECKED,
  },
  securityConfig: {
    title: "Network security configuration",
    url: "https://developer.android.com/privacy-and-security/security-config",
    publisher: "Android Developers",
    date: CHECKED,
  },
  windowSizeClasses: {
    title: "Use window size classes",
    url: "https://developer.android.com/develop/ui/compose/layouts/adaptive/use-window-size-classes",
    publisher: "Android Developers",
    date: CHECKED,
  },
  playTargetSdk: {
    title: "Meet Google Play's target API level requirement",
    url: "https://developer.android.com/google/play/requirements/target-sdk",
    publisher: "Google Play",
    date: CHECKED,
  },
  playTargetSdkHelp: {
    title: "Target API level requirements for Google Play apps",
    url: "https://support.google.com/googleplay/android-developer/answer/11926878",
    publisher: "Google Play",
    date: CHECKED,
  },
  appleUpcoming: {
    title: "Upcoming requirements",
    url: "https://developer.apple.com/news/upcoming-requirements/",
    publisher: "Apple Developer",
    date: CHECKED,
  },
  appleIphoneDuo: {
    title: "Prepare and submit your apps for iPhone Duo (Oct 5, 2026)",
    url: "https://developer.apple.com/news/?id=kkphp5qo",
    publisher: "Apple Developer",
    date: CHECKED,
  },
  appleIphoneDuoPrepare: {
    title: "Three steps to make your app shine on iPhone Duo",
    url: "https://developer.apple.com/iphone-duo/prepare/",
    publisher: "Apple Developer",
    date: CHECKED,
  },
  appleScreenshotSpecs: {
    title: "Screenshot specifications",
    url: "https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications",
    publisher: "Apple Developer",
    date: CHECKED,
  },
  wcag22: {
    title: "Web Content Accessibility Guidelines (WCAG) 2.2",
    url: "https://www.w3.org/TR/WCAG22/",
    publisher: "W3C",
    date: CHECKED,
  },
  wcagOrientation: {
    title: "Understanding SC 1.3.4: Orientation",
    url: "https://www.w3.org/WAI/WCAG22/Understanding/orientation.html",
    publisher: "W3C",
    date: CHECKED,
  },
  androidA11y: {
    title: "Make apps more accessible",
    url: "https://developer.android.com/guide/topics/ui/accessibility/apps",
    publisher: "Android Developers",
    date: CHECKED,
  },
  applePrivacyManifest: {
    title: "Privacy manifest files",
    url: "https://developer.apple.com/documentation/bundleresources/privacy-manifest-files",
    publisher: "Apple Developer",
    date: CHECKED,
  },
  playDataSafety: {
    title: "Provide information for Google Play's Data safety section",
    url: "https://support.google.com/googleplay/android-developer/answer/10787469",
    publisher: "Google Play",
    date: CHECKED,
  },
  androidVitals: {
    title: "Android vitals",
    url: "https://developer.android.com/topic/performance/vitals",
    publisher: "Android Developers",
    date: CHECKED,
  },
} satisfies Record<string, AuditRef>;

export type SourceId = keyof typeof SOURCES;
export const refs = (...ids: SourceId[]): AuditRef[] => ids.map((id) => SOURCES[id]);

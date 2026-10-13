# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for a security problem. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on the repository (private vulnerability reporting). If that isn't
available, open a minimal public issue asking for a private contact, without details.

Include what you found, how to reproduce it, and the version (`appscreenmap --version`). You can expect an
acknowledgement within a few days. This is a volunteer-run alpha project, so fixes are best-effort.

## Scope and things to know

AppScreenMap runs locally and drives a device or emulator through `adb` (or an iOS Simulator through `simctl` and `idb`). Points worth reviewing:

- **`appscreenmap serve`** serves the `runs/` folder and the viewer on `127.0.0.1` by default. Its only write
  endpoint accepts `PUT /runs/…/notes.json`, limited to the viewer's notes file, a size cap, a same-machine
  `Host` check, and existing run folders. Binding it to a public interface (`--host 0.0.0.0`) exposes your crawl
  data and that endpoint to the network. Don't.
- **Crawl output can contain sensitive data.** The crawler types test values into forms and stores screenshots
  and view hierarchies of whatever the app shows. Credentials from your config can end up in `map.json`, the
  Maestro flows and the trace. Use throwaway test accounts and review `runs/` before sharing or committing it.
- **The crawler taps real UI on the connected device.** It avoids labels like delete, pay and log out, but it is
  not a sandbox. Use an emulator or a test device.
- Dependencies are pinned in `uv.lock` and `web/bun.lock`.

## Supported versions

Only the latest release (or `main`) receives fixes.

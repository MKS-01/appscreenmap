# Third-party notices

AppScreenMap is MIT-licensed (see [LICENSE](LICENSE)). It includes or depends on the following.

## Included in the source tree

### Lucide icons (web viewer)

The inline SVG icon shapes in `web/src/components/Icon.tsx` are taken from [Lucide](https://lucide.dev), used
under the ISC license:

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT).
All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```

Check the upstream notice at <https://github.com/lucide-icons/lucide/blob/main/LICENSE> if you redistribute.

## Runtime dependencies (not vendored)

| Package | License | Used by |
|---|---|---|
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | crawler: screenshots, visual diff |
| [React](https://react.dev), React DOM | MIT | web viewer |
| [@xyflow/react](https://reactflow.dev) | MIT | web viewer: map canvas |
| [@dagrejs/dagre](https://github.com/dagrejs/dagre) | MIT | web viewer: graph layout |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) (optional) | MIT | `appscreenmap mcp` |

Build and dev tools (Vite, TypeScript, pytest, ruff, hatchling) are not redistributed.

## Maestro (flow format only)

AppScreenMap writes [Maestro](https://github.com/mobile-dev-inc/maestro) flow files (YAML) for each screen. Maestro
is licensed under Apache-2.0. AppScreenMap **does not include, link to, import or run Maestro code**: it only
generates text files in Maestro's documented flow syntax, and users run them with their own Maestro install.
Apache-2.0 and MIT are compatible, and generated flows are your own output. "Maestro" is a trademark of its
owners (mobile.dev); AppScreenMap is not affiliated with or endorsed by them, and uses the name only to describe
format compatibility.

## Prior art

AppScreenMap was inspired by [DroidBot](https://github.com/honeynet/droidbot),
[Fastbot](https://github.com/bytedance/Fastbot_Android) and [APE](https://github.com/tianxiaogu/ape). It shares
ideas, not code, with them.

## Sample data

`runs/` contains sample crawls of the sample-app app, which is maintained by the same author. Screenshots in
other apps' runs are not redistributed.

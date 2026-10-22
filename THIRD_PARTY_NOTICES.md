# Third-party notices

AppScreenMap is MIT-licensed (see [LICENSE](LICENSE)). It includes or depends on the following.

## Included in the source tree

### Lucide icons (web viewer)

The inline SVG icon shapes in `apps/viewer/src/components/Icon.tsx` are taken from or modelled on [Lucide](https://lucide.dev),
used under the ISC license. Lucide in turn includes portions derived from [Feather](https://feathericons.com) (MIT).
Both licenses follow:

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

```
The MIT License (MIT) (for portions derived from Feather)

Copyright (c) 2013-2022 Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Check the upstream notice at <https://github.com/lucide-icons/lucide/blob/main/LICENSE> if you redistribute.

## Fonts bundled into the viewer build

The viewer's UI font (Geist) and monospace font (Geist Mono) come from the `@fontsource-variable/geist` and
`@fontsource-variable/geist-mono` packages (npm dependencies, not in the source tree) and are bundled into the built
viewer (`apps/viewer/dist`) as `.woff2` files. They are licensed under the SIL Open Font License 1.1, which requires this notice and license to accompany any copy:

```
Copyright 2024 The Geist Project Authors (https://github.com/vercel/geist-font)

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is available with a FAQ at: https://openfontlicense.org

SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded,
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
```

## Runtime dependencies (not vendored)

| Package | License | Used by |
|---|---|---|
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | crawler: screenshots, visual diff |
| [React](https://react.dev), React DOM | MIT | web viewer |
| [@xyflow/react](https://reactflow.dev) | MIT | web viewer: map canvas |
| [@dagrejs/dagre](https://github.com/dagrejs/dagre) | MIT | web viewer: graph layout |
| [mcp](https://github.com/modelcontextprotocol/python-sdk) (optional) | MIT | `appscreenmap mcp` |

Vite bundles React, React DOM, `@xyflow/react` and `@dagrejs/dagre` into `apps/viewer/dist`; their MIT licenses are listed
above, and each package carries its own copyright notice. `mcp` brings its own dependencies when installed. Build and
dev tools (Vite, TypeScript, pytest, ruff, hatchling) are not redistributed.

## External tools (not bundled)

AppScreenMap runs these if you have installed them; it does not include or redistribute them: `adb` and `aapt2`
(Android SDK, Apache-2.0), `xcrun simctl` (Xcode), [idb](https://fbidb.io) and `idb_companion` (MIT), and, for the
security-audit skill only, `frida` (wxWindows Library Licence) and, for the by-hand code checks, `jadx` (Apache-2.0),
and, for `crawl --network`, [mitmproxy](https://github.com/mitmproxy/mitmproxy) (MIT), which loads our own addon.
The security scanner (`packages/security/`) was written from scratch for this project. It borrows ideas, not code,
from [mobile-recon](https://github.com/MKS-01/mobile-recon), an earlier MIT-licensed tool by the same author.

## Maestro (flow format only)

AppScreenMap writes [Maestro](https://github.com/mobile-dev-inc/maestro) flow files (YAML) for each screen. Maestro
is licensed under Apache-2.0. AppScreenMap **does not include, link to, import or run Maestro code**: it only
generates text files in Maestro's documented flow syntax, and users run them with their own Maestro install.
Apache-2.0 and MIT are compatible, and generated flows are your own output. "Maestro" is a trademark of its
owners (mobile.dev); AppScreenMap is not affiliated with or endorsed by them, and uses the name only to describe
format compatibility. Android and Google Play are trademarks of Google LLC; iOS, Xcode and Apple are trademarks of
Apple Inc. They are used only to say which platforms the tool works with, and AppScreenMap is not affiliated with
or endorsed by either company.

## Prior art

AppScreenMap was inspired by [DroidBot](https://github.com/honeynet/droidbot),
[Fastbot](https://github.com/bytedance/Fastbot_Android) and [APE](https://github.com/tianxiaogu/ape). It shares
ideas, not code, with them.

## Sample apps and sample runs

- **Playground** (`samples/playground-app/`): written for this project, MIT like the rest of the repo. Its APKs are
  release builds signed with the Android debug key.
- **Apache-2.0 components inside the binaries.** The Playground APKs, built with Jetpack Compose, contain AndroidX,
  Compose, Material 3 and the Kotlin standard library (Google and JetBrains, Apache-2.0). `samples/playground-app/gradle/wrapper/gradle-wrapper.jar` is Apache-2.0 too. Full text:
  <https://www.apache.org/licenses/LICENSE-2.0>.
- **Crawl output** (`runs/`) is git-ignored and not distributed with the project. `samples/demo.sh` generates crawls
  of the Playground: screenshots, view hierarchies and reports. The form values are dummy data (for example
  `demo@playground.dev`), and passwords appear only as `${APP_PASSWORD}` placeholders. Device screenshots can show
  Android or iOS system UI such as the status bar and keyboard; those belong to Google and Apple.

## Android skills

`.claude/skills/` holds unchanged copies of skills from <https://github.com/android/skills> (Google LLC, Apache-2.0; each folder carries
the license). `scripts/android-skills.lock` lists them and the commit they were synced at; `make skills-check` / `make skills-sync` keep them current.

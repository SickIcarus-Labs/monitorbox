# Third-party material

MonitorBox's own code is under the MIT licence (see `LICENSE`). It also bundles the following, which keep their own terms.

| What | Where | Licence |
| --- | --- | --- |
| Simple Icons marks | `app/monitorbox_app/icons` | CC0-1.0 |
| Dashboard Icons (homarr-labs/dashboard-icons) | `app/monitorbox_app/icons` | Apache-2.0 (covers the files; the logos they show remain the property of their owners, and their use here does not imply endorsement) |
| Sora and Figtree fonts | `app/monitorbox_app/brand` | SIL Open Font License 1.1 (texts beside the fonts) |
| Python and Node runtimes | container image | PSF licence and MIT, unmodified |

Apache-2.0 licence text: https://www.apache.org/licenses/LICENSE-2.0

The Scrypted module installs its own Node packages (listed in `modules/scrypted/package-lock.json`). Checked 2026-10-24 with license-checker: all 20 are permissive. MIT: @socket.io/component-emitter, balanced-match, brace-expansion, debug, engine.io-client, engine.io-parser, follow-redirects, ms, ws, xmlhttprequest-ssl. ISC: @scrypted/client, @scrypted/types. BlueOak-1.0.0: glob, lru-cache, minimatch, minipass, package-json-from-dist, path-scurry, rimraf. Apache-2.0: openai.

# Mobile teacher app — 30 October 2026

Prepared UI update; not automatically deployed to the user's server.

## Changes

- Mobile teacher-only shell: five persistent icon tabs (Today, Schedule, Chats, Students, Menu), one compact sticky heading and a homework shortcut. Existing navigation handlers remain the owner of routing. Booking and Telemost remain available in Menu.
- Active chat has its own toolbar. Student actions are behind an accessible ellipsis button. The history uses available visual viewport height, with an attachment, text, channel chooser and send button in one composer row. Existing send, channel-selection, attachment and draft handlers are retained. Navigation is hidden when an iPhone keyboard reduces the visual viewport.
- Group tabs scroll horizontally without wrapping/colliding. Group metrics, forms and headings use a compact mobile density.
- Library and formula hero copy is collapsed; PDF upload remains reachable. Search stays visible. Subject/grade/sort selects open in a modal bottom sheet and return to their original DOM position, retaining values and listeners.
- PWA teacher manifest keeps its existing id and branding, but starts directly at /app/teacher.html with /app/ scope. This matches the real redirected page and avoids immediately leaving /teacher/ scope. display remains standalone. This does not hide Safari chrome in an ordinary browser tab or grant offline functionality. Existing iOS home-screen entries may need to be recreated to adopt the corrected launch configuration. No push subscriptions or service workers are removed by the installer.
- CSS only activates at <=900px with the mobile shell marker. Existing desktop layout stays in place. Electron role assets include the module for future builds; the live site gets the same modules through HTML.

## Install

From an isolated source checkout, run scripts/install_release_ui.py (preflight), then --apply. It retains unrelated production HTML and manifest fields, checks existing module hashes, backs up changed files, verifies web health and the exact served CSS/JS bytes, and rolls back files on failure. It does not change lesson data or credentials.

## Verification

- teacher_mobile_app_selftest.cjs: existing route and drawer activation, chat action/channel toggles, original send handler, draft/file input identity, filter select handler/value retention, restoration and repeat initialization.
- teacher_mobile_cascade_selftest.cjs: precedence against existing chat, composer, group and formula styles at 375, 390, 430, 768 and 900px. Group tabs do not wrap, upload button remains displayed, filter select is displayed in the sheet.
- Existing mobile navigation, release UI and studio desktop cascade checks pass.
- Installer tested with captured public production HTML: additive tags are idempotent; manifest id and custom icon remain, start_url and shortcuts remain inside scope.

These are DOM and CSS cascade checks, not a real iPhone/Safari render. Device validation remains required after deployment: chat with keyboard, actual file/send/channel selection, group tabs, filter sheet, library PDF upload, installed home-screen launch. Actual message delivery was not exercised or triggered by this update.

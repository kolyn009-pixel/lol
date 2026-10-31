# Adelia 0.3.0-beta.10 — release candidate

This commit adds a shared cabinet UI foundation for teacher, student and parent
pages and packages the same assets in Electron's role bundle. It improves button,
input, card, chat, finance, formula and post-lesson typography and spacing. It does
not replace the underlying page renderers or introduce new payment/lesson actions.

The release widget adds keyboard-accessible About/What's new, tooltips using
existing accessible labels, active navigation semantics, connectivity feedback and
a bridge to the native About/updater. It never wraps fetch, disables form submits,
clears inputs, stores private drafts or shows an invented delivery/saved status.
Existing messaging modules remain responsible for delivery and draft persistence.

The native About page has larger text, responsive layout and release notes. The
version is beta.10. Existing single-window lesson views and update guards remain.
The local Intel Mac builder now verifies/pulls the Windows builder image before
building either Mac package, with three attempts. A Docker Hub timeout therefore
fails before expensive application packaging begins.

## Install shared UI

Use an isolated checkout of the exact release commit:

```
python3 scripts/install_release_ui.py --root /opt/adelia-current --apply
```

The installer preserves production HTML, verifies the active web working directory,
backs up changes and rolls back on failed restart, API health or served static-byte
checks. It does not change the database or publish desktop installers.

## Build

On the owner's Intel Mac, clone the exact release commit to a fresh folder, then:

```
bash scripts/build_all_on_intel_mac.sh
```

This runs repository selftests and builds Mac x64, Mac arm64 and Windows x64. It
checks the generated manifests and SHA512 values before producing the platform
ZIPs. Native builds are not produced by this Linux workspace. Existing beta.9
files are not beta.10 and must not be relabeled or published as this release.

## Verification completed here

- Shared UI DOM checks: network transitions, unchanged draft text, active nav,
  accessible tooltips, modal close/focus, native About and existing install action.
- Existing student draft selftest: navigation retains text; successful send clears.
- Unified lesson-room mocked Electron test: isolated views, owned IPC, login popup,
  layout focus and cleanup.
- JavaScript syntax, stylesheet parsing and shell/Python installer syntax.

These checks are not a substitute for a native visual and end-to-end check.

## Native checks still required before publishing to clients

1. Install on Intel Mac and Windows, keeping the existing user-data/session folder.
2. Verify login/session retention; inspect at 1280x800 and a narrow window.
3. Start a test lesson: board, actual Telemost call, camera/mic and Yandex login.
4. Finish it: topic selection, saved review and correct financial/attendance state.
5. Check chat navigation draft and actual Telegram/VK delivery statuses.
6. Open olympiad month/week/agenda, preparation and a test student's results.
7. Verify About/update prompt, active-lesson protection, replacement of old app.
8. Smoke-check Apple Silicon package on that hardware when available.

Do not call this release verified for live calls or all platforms before those
checks. Publishing should use all three manifests with the same version and SHA;
no desktop feed or client auto-update is changed by the website installer.

## Mobile navigation hotfix

At <=900px the teacher sidebar uses a closed-by-default off-canvas drawer. The
existing menu button and menu-open state are reused; capture-phase routing
prevents a legacy click handler from toggling twice. Backdrop, Escape and menu
selection close the drawer; background main content is inert while it is open.
A wider viewport clears inert/menu state. Explicit install instructions remain
available, while all three legacy install-promotion overlays are hidden. Shared
asset query versions are refreshed by the installer, including already-added tags.
DOM checks cover these transitions; an actual iPhone visual check remains needed.

## Mobile correction, 30 October 2026

Live studio4 desktop CSS had more specific `!important` selectors than the first mobile fix. On phones it kept an invisible sidebar in normal flow with max-height 220px and hid the menu trigger. The mobile scope now overrides that exact production selector, takes the drawer out of flow and uses an explicit two-row header. Small dashboard action cards hide secondary captions; next-lesson content aligns to the left.

`scripts/mobile_cascade_selftest.cjs` reproduces the old cascade conflict and checks the new rules at 375, 390, 430, 768, 900, 901 and 1440px in both studio4 and native theme markers. Existing menu gesture tests also pass. CSS cascade and DOM checks are not an actual iPhone render; user confirmation after deployment is still needed. Desktop layout above 900px retains its theme.

# Telemost compatibility candidate 0.3.1

Observed in 0.3.0 on Windows: the embedded Telemost page reports that its version is obsolete. A valid meeting URL is not evidence of browser compatibility.

The room and fallback meeting windows now remove only Electron/Adelia product tokens from their User-Agent before navigation, retaining the actual Chromium version, OS, sandbox, origin restrictions and existing authentication partition. Login windows receive the same browser profile. No permissions are broadened and no cookie or storage clearing is performed.

Added explicit Telemost-only reload with call-interruption confirmation and an optional trusted meeting URL opened in the system browser, with an echo warning. Board and context stay in Adelia. The provider error is not hidden or replaced with a success state.

Evidence: fetched current provider web bundle contains a navigator.userAgent Electron check, while the room previously used the default Electron User-Agent. This is a compatibility hypothesis, not a reproduced and confirmed root cause of the screenshot. Public landing-page HTTP requests classified both example UAs as Chrome and supported Telemost; that alone does not demonstrate successful joining or disprove client-side detection or cached resources.

Node tests cover UA cleaning and idempotence, unchanged engine/OS versions, application before meeting load, original auth partition, unchanged board UA, trusted URLs and reload/external confirmations. Native build and actual video call, login, camera, microphone and screen sharing require testing on Windows and Mac after rebuilding.

Build scripts/build_all_on_intel_mac.sh from this commit. Publish with scripts/publish_uploaded_desktop.py --git-sha FULL_SHA only after device checks. This creates version 0.3.1; do not replace 0.3.0 installers in-place. A server CSS/JS install cannot update native lesson_room.js.

## Board account addition

The room toolbar now has an explicit board-account action. It opens the board service's own account page in a sandboxed modal with the same persist:adelia-board partition as the working board. MoyaDoska's public client was inspected: its OAuth flows use oauth.yandex.ru and id.vk.com and return to app.moyadoska.com. Exact provider origins and board origins are allowed in navigation/popups; arbitrary redirects are blocked. No passwords or provider tokens are collected by Adelia. The user registers or signs in themselves.

Closing the account window reloads the original board to apply the shared session. The opening confirmation tells the user to wait for saving first. Closing does not imply successful login and no fake signed-in label is displayed. Existing board/Telemost partitions remain separate. Native registration/sign-in through provider pages remains to be tested; third-party requirements may block embedded authentication.

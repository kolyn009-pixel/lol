# Stage 12 — pre-production privacy/security checklist

Code hardening is designed to stay lightweight: no external security service is called on normal requests; session/ownership checks remain local SQLite queries; expensive PBKDF2 is used only for password authentication.

Before switching production to `web_backend.api_v3`:

- Generate a long random `ADELIA_OTP_SECRET` directly on the server (at least 32 bytes of entropy). Never commit it to GitHub or store it in `tutor.db`.
- Provide `ADELIA_OTP_SECRET` to `adelia-web.service` through a root-readable environment file or systemd credential/environment configuration. Protect the file from non-root users.
- Confirm the service still binds only to `127.0.0.1:8765`; do not expose the Python HTTP server directly to the Internet.
- Confirm nginx proxies only to `127.0.0.1:8765` and sends `Host $host`, `X-Real-IP $remote_addr`, and `X-Forwarded-For $proxy_add_x_forwarded_for`.
- Confirm HTTP redirects to HTTPS and the TLS certificate is valid. Add/verify HSTS at nginx after HTTPS behavior is confirmed.
- Run `python -m web_backend.stage12_security_selftest` with the same environment as the web service. It must pass before restart/cutover.
- Smoke-test student, parent, OWNER and ADMIN logins. Confirm TESTER cannot obtain a teacher web session.
- IDOR smoke-test with two students: student A must get 404/denial for student B homework, lesson join, material and other student-owned IDs. Repeat parent A against an unlinked child.
- Confirm cross-origin POST with a foreign `Origin` returns 403 while normal same-origin writes work through nginx.
- Confirm auth endpoints return 429 after repeated failed attempts from one client IP and that different client IPs are not accidentally grouped behind nginx.
- Confirm session cookie has `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and a bounded `Max-Age`; `/api/auth/me` must not expose entity IDs or session tokens.
- Confirm logout invalidates the server-side session. Confirm student password reset invalidates older student sessions/devices.
- Upload a valid PDF and reject a non-PDF/oversized upload. Confirm protected material URLs cannot be opened by another student.
- Check logs: request query strings, cookies, OTPs, passwords and request bodies must not be printed.
- Verify backups/storage permissions for `/opt/tutorbot/tutor.db` and `/opt/tutorbot/storage/materials`; neither should be served by nginx as static content.
- After cutover, check response headers on HTML/API: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, COOP/CORP.
- Check latency for student dashboard, teacher inbox and session-authenticated API calls before/after cutover. Investigate regressions rather than weakening ownership/session checks.

Do not delete the legacy SHA-256 OTP compatibility path until all OTPs issued before the HMAC deployment have expired (current TTL is 10 minutes). After that migration window, remove legacy digest acceptance in a later cleanup commit.

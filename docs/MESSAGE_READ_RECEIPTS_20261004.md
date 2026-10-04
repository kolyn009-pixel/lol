# Student delivery and read receipts

- Teacher sends a read acknowledgement only after rendering the active conversation, while the page is visible and the history is at its latest messages. New messages are acknowledged after polling renders them; background tabs do not acknowledge.
- Each acknowledgement includes the highest loaded message ID. Messages arriving after that snapshot remain unread. Server updates only incoming messages in the requested conversation. First read timestamp is immutable, explicitly UTC and survives restarts.
- Legacy student read flags are updated only for mapped messages in that student's conversation. Opening a parent thread does not clear the student's unread messages.
- Student sees Sent (accepted on the server), Delivered (delivered to teacher inbox), or Read with date/time in the saved StudentTime region. Queued messages remain Sent. No claim of native Telegram/VK device-level delivery/read receipts is made.
- New timestamps include an offset. Historical naive timestamps are interpreted using the server local timezone, matching the existing database.now_iso writer, then serialized as UTC. No bulk rewrite of historical data.
- Student history polling is every four seconds while visible. Region changes refresh timestamps. This is polling, not a WebSocket guarantee of instantaneous updates.

Validation: isolated SQLite read-boundary/idempotency/parent-scope tests; student Moscow/Samara/Tokyo date-rollover tests; teacher visibility and concurrent-arrival tests; existing student and teacher messenger tests; syntax checks. Added tests to CI and bumped relevant web/PWA asset versions. Visual and live two-account verification remains necessary after server deployment.

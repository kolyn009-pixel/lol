# VK multichannel adapter

VK is a second transport for the existing TutorBot domain model.

Design invariants:
- one TutorBot user record, multiple channel identities;
- Telegram and VK share lessons, payments, balances, homework and schedules;
- blocking one transport must not deactivate the student globally;
- account linking uses short-lived one-time codes, never name matching;
- VK UI uses native keyboards while keeping the same product actions as Telegram;
- VK secrets live only in server environment variables.

Initial environment:
- VK_GROUP_ID
- VK_TOKEN
- VK_API_VERSION (default 5.199)

Implementation phases:
1. identity/link schema and migration;
2. Long Poll transport + native keyboard renderer;
3. linked-user main menu and schedule read path;
4. booking/payment/homework actions through shared services;
5. per-channel delivery availability and reminders.

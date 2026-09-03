# ADELIA RC1

Release candidate for /opt/tutorbot.

## Changes in RC1
- Restored students navigation: Students -> grade -> student list -> student card.
- Added student counts by grade and blocked-students shortcut.
- Added explicit Main menu button to teacher admin menu.
- Preserved student block/unblock with Telegram notification and retained data.
- Preserved silent channel JOIN/LEAVE tracking and daily channel report.
- Preserved Adelia-assisted channel post drafting with confirmation before publish.
- Preserved Adelia-assisted broadcasts to all students, EGE/OGE, subject and grade segments with preview and confirmation.
- Preserved student-card Adelia messaging and contextual assistant.

## Safety
Deployment script preserves tutor.db, venv, credentials.json, token.json, .env and backups.

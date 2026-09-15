"""Adelia web API v7: Google reconnect, groups and Telemost lifecycle."""
from __future__ import annotations
from datetime import datetime
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from web_backend import api as v1, api_v6, event_campaign, formula_schema_repair, google_calendar_oauth, group_lessons, group_portal, open_event_admin, otp_secret, public_trial_access, public_trial_channel, student_on
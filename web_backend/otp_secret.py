"""Keyed digest helper for short-lived web OTPs.

A six-digit OTP has only one million possible values, so an ordinary SHA-256
hash can be brute-forced offline if tutor.db is copied. HMAC binds the digest to
a server-side secret that must not be stored in the database or repository.

Set ADELIA_OTP_SECRET to a long random value in the web service environment.
"""
from __future__ import annotations

import hashlib
import hmac
import os

ENV_NAME = "ADELIA_OTP_SECRET"
MIN_SECRET_BYTES = 32
PREFIX = "h1$"


def configured():
    value = os.environ.get(ENV_NAME, "").encode("utf-8")
    return len(value) >= MIN_SECRET_BYTES


def _key():
    value = os.environ.get(ENV_NAME, "").encode("utf-8")
    if len(value) < MIN_SECRET_BYTES:
        raise RuntimeError("adelia_otp_secret_missing")
    return value


def digest(code):
    raw = str(code or "").strip().encode("utf-8")
    return PREFIX + hmac.new(_key(), raw, hashlib.sha256).hexdigest()


def legacy_sha256(code):
    return hashlib.sha256(str(code or "").strip().encode("utf-8")).hexdigest()


def candidates(code):
    """HMAC first, legacy SHA second for a one-release migration window."""
    values = []
    try:
        values.append(digest(code))
    except RuntimeError:
        pass
    values.append(legacy_sha256(code))
    return values

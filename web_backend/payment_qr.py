"""Private teacher-managed payment QR. The image is never part of public web assets."""
from __future__ import annotations

import base64
import binascii
import os
import secrets
import struct
from pathlib import Path

MAX_BYTES = 1024 * 1024
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
ROOT = Path(os.environ.get('ADELIA_PAYMENT_QR_DIR', '/opt/tutorbot/data/parent_payment_qr'))
FILE = ROOT / 'qr.png'


def status():
    return {'configured': FILE.is_file(), 'max_bytes': MAX_BYTES, 'format': 'PNG'}


def save_png(content_b64):
    encoded = str(content_b64 or '')
    if not encoded or len(encoded) > (MAX_BYTES * 4 // 3 + 8):
        raise ValueError('invalid_qr_size')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('invalid_qr_data') from None
    return save_png_bytes(raw)


def save_png_bytes(raw):
    if len(raw) < 33 or len(raw) > MAX_BYTES or not raw.startswith(PNG_MAGIC) or raw[12:16] != b'IHDR':
        raise ValueError('invalid_qr_png')
    width, height = struct.unpack('>II', raw[16:24])
    if not (80 <= width <= 4096 and 80 <= height <= 4096):
        raise ValueError('invalid_qr_dimensions')
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        ROOT.chmod(0o700)
    except OSError:
        pass
    temp = ROOT / ('qr-' + secrets.token_hex(12) + '.tmp')
    try:
        with temp.open('xb') as f:
            os.chmod(temp, 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, FILE)
    finally:
        temp.unlink(missing_ok=True)
    return status()


def read_png():
    try:
        data = FILE.read_bytes()
    except FileNotFoundError:
        raise ValueError('qr_not_configured') from None
    if not data.startswith(PNG_MAGIC) or len(data) > MAX_BYTES:
        raise ValueError('invalid_qr_png')
    return data


def send_png(handler):
    try:
        data = read_png()
    except ValueError:
        return handler._json(404, {'error': 'qr_not_configured'})
    handler.send_response(200)
    handler.send_header('Content-Type', 'image/png')
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Content-Disposition', 'inline; filename="payment-qr.png"')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Cache-Control', 'private, no-store, max-age=0')
    handler.end_headers()
    handler.wfile.write(data)

from __future__ import annotations

"""Read-only concurrency probe for Adelia's public trial slot endpoint.

Defaults are intentionally conservative and safe for pre-production: 100
concurrent clients, one GET request each, no writes and no authentication. The
script reports latency percentiles and fails on transport/HTTP errors or when
p95 exceeds the configured budget.
"""

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request


def percentile(values, p):
    if not values:
        return 0.0
    xs = sorted(values)
    idx = min(len(xs) - 1, max(0, int(round((len(xs) - 1) * p))))
    return xs[idx]


def one(url, timeout):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
        elapsed = time.perf_counter() - started
        if status != 200:
            return {"ok": False, "status": status, "seconds": elapsed, "error": "http_status"}
        try:
            payload = json.loads(body.decode("utf-8"))
            slots = sum(len(day.get("slots", [])) for day in payload.get("items", []))
        except Exception:
            slots = None
        return {"ok": True, "status": status, "seconds": elapsed, "slots": slots}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": int(exc.code), "seconds": time.perf_counter() - started, "error": "http_error"}
    except Exception as exc:
        return {"ok": False, "status": None, "seconds": time.perf_counter() - started, "error": type(exc).__name__}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--clients", type=int, default=100)
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--p95-budget", type=float, default=2.0)
    args = ap.parse_args()

    clients = max(1, min(args.clients, 300))
    total = max(1, min(args.requests, 2000))
    url = args.base_url.rstrip("/") + "/api/public/trial/slots?timezone=Europe%2FMoscow&days=14&duration_minutes=60"

    wall_started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=clients) as pool:
        results = list(pool.map(lambda _: one(url, args.timeout), range(total)))
    wall = time.perf_counter() - wall_started

    good = [x for x in results if x["ok"]]
    bad = [x for x in results if not x["ok"]]
    lat = [x["seconds"] for x in good]
    status_counts = {}
    for row in results:
        key = str(row.get("status"))
        status_counts[key] = status_counts.get(key, 0) + 1

    report = {
        "url": url,
        "clients": clients,
        "requests": total,
        "ok": len(good),
        "failed": len(bad),
        "wall_seconds": round(wall, 3),
        "requests_per_second": round(total / wall, 2) if wall else 0,
        "latency_seconds": {
            "median": round(statistics.median(lat), 3) if lat else None,
            "p95": round(percentile(lat, 0.95), 3) if lat else None,
            "max": round(max(lat), 3) if lat else None,
        },
        "status_counts": status_counts,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if bad:
        return 2
    if lat and percentile(lat, 0.95) > float(args.p95_budget):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

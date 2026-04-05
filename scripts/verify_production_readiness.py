#!/usr/bin/env python3
"""
تحقق سريع من جاهزية الخادم للإنتاج ولتطبيق عميل (أندرويد / اختبار يدوي).

الاستخدام:
  set BASE_URL=https://your-domain.com
  py scripts/verify_production_readiness.py

أو:
  BASE_URL=https://127.0.0.1:8000 py scripts/verify_production_readiness.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx", file=sys.stderr)
    raise SystemExit(2)


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _fail(msg: str, detail: str = "") -> None:
    print(f"[FAIL] {msg}" + (f" — {detail}" if detail else ""))


def main() -> int:
    base = (os.getenv("BASE_URL") or "").strip().rstrip("/")
    if not base:
        _fail("BASE_URL غير معرّف", "مثال: set BASE_URL=https://api.example.com")
        return 1

    timeout = float(os.getenv("READINESS_TIMEOUT", "15"))
    headers: dict[str, str] = {"X-App-Version": "readiness-check", "Accept": "application/json"}

    checks: list[tuple[str, str, dict[str, Any]]] = [
        ("GET", f"{base}/health", {"status": 200, "json_key": "status", "json_value": "ok"}),
        ("GET", f"{base}/health/ready", {"status": 200, "json_key": "status", "json_value": "ready"}),
        ("GET", f"{base}/api/v1/health", {"status": 200, "json_key": "status", "json_value": "ok"}),
        ("GET", f"{base}/api/v1/meta", {"status": 200, "json_key": "api_version", "json_value": "1"}),
    ]

    failed = 0
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for method, url, expect in checks:
            try:
                r = client.request(method, url, headers=headers)
            except Exception as exc:
                _fail(f"{method} {url}", str(exc))
                failed += 1
                continue
            if r.status_code != expect["status"]:
                _fail(f"{method} {url}", f"status {r.status_code}, expected {expect['status']}")
                failed += 1
                continue
            try:
                data = r.json()
            except Exception:
                _fail(f"{method} {url}", "response is not JSON")
                failed += 1
                continue
            key = expect["json_key"]
            if data.get(key) != expect["json_value"]:
                _fail(f"{method} {url}", f"{key}={data.get(key)!r}, expected {expect['json_value']!r}")
                failed += 1
                continue
            _ok(f"{method} {url}")

        # رؤوس موحّدة للعميل
        try:
            r = client.get(f"{base}/api/v1/meta", headers=headers)
            if r.headers.get("X-API-Version") != "1":
                _fail("رأس X-API-Version", f"got {r.headers.get('X-API-Version')!r}")
                failed += 1
            else:
                _ok("رأس X-API-Version == 1")
            if r.headers.get("X-App-Version-Accepted") != "readiness-check":
                _fail("رأس X-App-Version-Accepted", f"got {r.headers.get('X-App-Version-Accepted')!r}")
                failed += 1
            else:
                _ok("رأس X-App-Version-Accepted يعكس الطلب")
        except Exception as exc:
            _fail("فحص الرؤوس", str(exc))
            failed += 1

    if failed:
        print(f"\nأنهى بـ {failed} فشل.")
        return 1
    print("\nكل الفحوصات الأساسية نجحت.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

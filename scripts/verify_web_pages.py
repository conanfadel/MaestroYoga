import http.cookiejar
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.web_shared import PUBLIC_INDEX_DEFAULT_PATH

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def main() -> None:
    print("root", urllib.request.urlopen(f"{BASE}/", timeout=5).status)
    index_html = urllib.request.urlopen(f"{BASE}{PUBLIC_INDEX_DEFAULT_PATH}", timeout=5).read().decode(
        "utf-8"
    )
    print("index_ok", "الجلسات المتاحة" in index_html)
    print("admin_login_get", urllib.request.urlopen(f"{BASE}/admin/login", timeout=5).status)

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    login_data = urllib.parse.urlencode(
        {"email": "owner@maestroyoga.local", "password": "Admin@12345"}
    ).encode()
    login_resp = opener.open(f"{BASE}/admin/login", data=login_data, timeout=5)
    print("admin_after_login", login_resp.geturl())

    room_data = urllib.parse.urlencode({"name": "QA Room", "capacity": "11"}).encode()
    room_resp = opener.open(f"{BASE}/admin/rooms", data=room_data, timeout=5)
    print("room_create", room_resp.geturl())

    admin_html = opener.open(f"{BASE}/admin", timeout=5).read().decode("utf-8")
    print("admin_has_room", "QA Room" in admin_html)

    # Current flow requires authenticated + verified public users before booking.
    booking_data = urllib.parse.urlencode({"center_id": "1", "session_id": "1"}).encode()
    booking_resp = urllib.request.urlopen(
        urllib.request.Request(f"{BASE}/public/book", data=booking_data, method="POST"),
        timeout=5,
    )
    print("public_book_redirect", booking_resp.geturl())


if __name__ == "__main__":
    main()

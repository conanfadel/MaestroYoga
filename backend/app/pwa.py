"""مسارات PWA: manifest يعكس إصدار التطبيق، وعامل خدمة خفيف لتحديثات الكاش."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

try:
    from .app_version import APP_VERSION_STRING
except ImportError:
    from backend.app.app_version import APP_VERSION_STRING  # type: ignore[no-redef]

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "static" / "manifest.json"

pwa_router = APIRouter(tags=["pwa"])


def _load_manifest_template() -> dict:
    try:
        with _MANIFEST_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {
            "name": "Maestro Yoga",
            "short_name": "Maestro Yoga",
            "description": "حجز جلسات اليوغا والاشتراكات والدفع الإلكتروني",
            "start_url": "/index?center_id=1",
            "scope": "/",
            "display": "standalone",
            "orientation": "natural",
            "background_color": "#fafcfb",
            "theme_color": "#c5a059",
            "lang": "ar",
            "dir": "rtl",
            "icons": [
                {
                    "src": "/static/icons/pwa-icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
        }


def build_manifest_payload() -> dict:
    data = _load_manifest_template()
    data["version"] = APP_VERSION_STRING
    return data


def build_service_worker_js() -> str:
    v = json.dumps(APP_VERSION_STRING)
    return f"""const CACHE = 'maestro-yoga-' + {v};
self.addEventListener('install', (e) => {{
  self.skipWaiting();
}});
self.addEventListener('activate', (e) => {{
  e.waitUntil((async () => {{
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((k) => k.startsWith('maestro-yoga-') && k !== CACHE).map((k) => caches.delete(k))
    );
    await self.clients.claim();
  }})());
}});
"""


@pwa_router.get("/manifest.json")
def pwa_manifest() -> JSONResponse:
    return JSONResponse(
        content=build_manifest_payload(),
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@pwa_router.get("/sw.js")
def service_worker() -> Response:
    return Response(
        content=build_service_worker_js(),
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )

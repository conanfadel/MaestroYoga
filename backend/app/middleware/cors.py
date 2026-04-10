"""Optional CORS for browser / WebView clients."""

from __future__ import annotations


def attach_cors(app, origins: list[str]) -> None:
    """CORS اختياري لمتصفحات أخرى منشأها أو WebView يفحص CORS."""
    if not origins:
        return
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "Retry-After",
            "X-API-Version",
            "X-App-Version-Accepted",
            "X-RateLimit-Remaining",
            "X-RateLimit-Limit-Window",
        ],
    )

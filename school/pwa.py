"""
Progressive Web App endpoints: manifest, service worker and offline fallback.

Why these are Django views rather than plain static files:

  * The **service worker must be served from the site root** (`/service-worker.js`).
    A worker's default scope is its own directory, so one served from
    `/static/js/` could only control `/static/js/*`. Serving it from `/` (and
    sending `Service-Worker-Allowed: /`) lets it control the whole app.
  * The manifest embeds values that live in settings (app name, theme colour,
    start URL), so generating it keeps a single source of truth.

Caching policy — deliberately conservative, because this is a multi-tenant app:

    Mero Attendance serves per-organisation data behind a login. If the worker
    cached HTML responses, a shared or handed-over device could redisplay one
    organisation's dashboard to whoever opens the app next, straight from disk,
    with no request to the server. So:

      - HTML/navigation  -> network-first, response is NEVER written to cache;
                            on failure we serve the generic offline page.
      - Static assets    -> stale-while-revalidate (safe: no tenant data).
      - Anything non-GET -> passed straight through, never intercepted.
      - /media/, /logout, /admin -> always bypassed.
"""

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static as static_url
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt

APP_NAME = "Mero Attendance"
APP_SHORT_NAME = "Mero"
THEME_COLOR = "#dc2626"
BACKGROUND_COLOR = "#ffffff"


def manifest(request):
    """Web app manifest. `display: standalone` is what makes it open in its own
    window (no browser chrome) so it feels like a desktop app."""
    icons = [
        {"src": static_url("pwa/icon-96.png"), "sizes": "96x96", "type": "image/png", "purpose": "any"},
        {"src": static_url("pwa/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": static_url("pwa/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": static_url("pwa/icon-maskable-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
        {"src": static_url("pwa/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    data = {
        "id": "/",
        "name": APP_NAME,
        "short_name": APP_SHORT_NAME,
        "description": "Attendance, HRMS, payroll and school management for your organisation.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        # Desktop browsers honour this ordering; if the OS can't do standalone
        # it degrades gracefully rather than falling all the way back to a tab.
        "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
        "orientation": "any",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "lang": "en",
        "dir": "ltr",
        "categories": ["business", "productivity", "education"],
        "icons": icons,
        # Right-click / long-press the installed app icon to jump straight in.
        "shortcuts": [
            {"name": "Dashboard", "short_name": "Dashboard", "url": "/",
             "icons": [{"src": static_url("pwa/icon-192.png"), "sizes": "192x192"}]},
            {"name": "My Attendance", "short_name": "Attendance", "url": "/staff/my-attendance/",
             "icons": [{"src": static_url("pwa/icon-192.png"), "sizes": "192x192"}]},
            {"name": "Notices", "short_name": "Notices", "url": "/staff/notices/",
             "icons": [{"src": static_url("pwa/icon-192.png"), "sizes": "192x192"}]},
            {"name": "Apply for Leave", "short_name": "Leave", "url": "/staff/apply-leave/",
             "icons": [{"src": static_url("pwa/icon-192.png"), "sizes": "192x192"}]},
        ],
    }
    resp = JsonResponse(data)
    resp["Content-Type"] = "application/manifest+json"
    resp["Cache-Control"] = "public, max-age=3600"
    return resp


# The worker itself must never be cached, or clients get stuck on an old
# version and stop picking up updates.
@csrf_exempt
@cache_control(no_cache=True, no_store=True, must_revalidate=True, max_age=0)
def service_worker(request):
    precache = [
        static_url("assets/css/soft-ui-dashboard.css"),
        static_url("css/mero-theme.css"),
        static_url("assets/css/nucleo-icons.css"),
        static_url("assets/css/nucleo-svg.css"),
        static_url("assets/js/core/bootstrap.min.js"),
        static_url("assets/js/core/popper.min.js"),
        static_url("assets/js/soft-ui-dashboard.min.js"),
        static_url("pwa/icon-192.png"),
        static_url("pwa/icon-512.png"),
    ]
    body = render(request, "pwa/service-worker.js", {
        "precache_urls": precache,
        "offline_url": "/offline/",
        # Bumping this string is what triggers the update flow on clients.
        "cache_version": getattr(settings, "PWA_CACHE_VERSION", "v1"),
    }, content_type="application/javascript")
    # Lets a worker served from / control every path on the origin.
    body["Service-Worker-Allowed"] = "/"
    return body


def offline(request):
    """Shown when a navigation is attempted with no usable connection."""
    return render(request, "pwa/offline.html", status=200)

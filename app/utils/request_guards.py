"""
Request-level guards, applied to every route as ASGI middleware:

- BodySizeLimit: rejects oversized POST bodies before the multipart parser
  spools them to disk.
- SameOriginCheck: CSRF defence. A browser always sends Origin (or Referer)
  with a cross-site POST; if it names another site, the request is refused.
  Scripts using an API key send neither header and are let through.
- HeadAsGet: FastAPI GET routes answer HEAD with 405, so link checkers,
  uptime monitors and status badges report the site as down. A HEAD request
  is served as GET and only the headers are sent back. GET links that change
  something (email opt-out and admin links, OAuth, logout) keep refusing HEAD,
  because mail scanners check links with HEAD; view counters skip HEAD.
"""
import json
import re
from contextvars import ContextVar
from urllib.parse import urlsplit

from app.config import settings

MB = 1024 * 1024
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

DEFAULT_BODY_LIMIT = (8 * MB, "Request too large.")
# (path pattern, limit, message): the library allows a 20 MB file plus form overhead
_BODY_LIMITS = [
    (re.compile(r"^/library/entry/\d+/files$"), 21 * MB, "Files can be at most 20 MB."),
]


async def _send_json(send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})


class BodySizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in _UNSAFE_METHODS:
            return await self.app(scope, receive, send)

        limit, message = DEFAULT_BODY_LIMIT
        for pattern, n, msg in _BODY_LIMITS:
            if pattern.match(scope["path"]):
                limit, message = n, msg
                break

        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            try:
                too_big = int(length) > limit
            except ValueError:
                too_big = True
            if too_big:
                return await _send_json(send, 413, {"error": message})

        # No Content-Length (chunked upload): count as it arrives and cut it off.
        received = 0

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    return {"type": "http.disconnect"}
            return msg

        await self.app(scope, limited_receive, send)


def _own_hosts(headers: dict) -> set[str]:
    hosts = {urlsplit(settings.SITE_URL).netloc.lower()}
    for name in (b"host", b"x-forwarded-host"):
        for h in headers.get(name, b"").decode("latin-1").split(","):
            if h.strip():
                hosts.add(h.strip().lower())
    return hosts


class SameOriginCheck:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in _UNSAFE_METHODS:
            headers = dict(scope["headers"])
            source = headers.get(b"origin") or headers.get(b"referer")
            if source is not None:
                source_host = urlsplit(source.decode("latin-1")).netloc.lower()
                if source_host not in _own_hosts(headers):
                    return await _send_json(send, 403, {"error": "Cross-site request refused."})
        await self.app(scope, receive, send)


# True while a HEAD request is being served as GET (checked by the view counters).
is_head_request: ContextVar[bool] = ContextVar("is_head_request", default=False)

# GET links with side effects: a HEAD here must not trigger them.
_NO_HEAD = re.compile(r"^/(notify/opt-out/|admin/(citation-approve|email-login|login/)|auth/)")


class HeadAsGet:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "HEAD":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path.startswith("/static/"):
            # StaticFiles answers HEAD itself without reading the file.
            return await self.app(scope, receive, send)
        if _NO_HEAD.match(path):
            return await _send_json(send, 405, {"error": "Method Not Allowed"})

        # Headers (including Content-Length) stay as for GET; the body is dropped.
        async def send_headers_only(message):
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return
                message = {"type": "http.response.body", "body": b""}
            await send(message)

        token = is_head_request.set(True)
        try:
            await self.app(dict(scope, method="GET"), receive, send_headers_only)
        finally:
            is_head_request.reset(token)

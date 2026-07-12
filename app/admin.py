import hmac
import logging
import secrets
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    abort,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import db, get_conn

bp = Blueprint("admin", __name__)
oauth = OAuth()
log = logging.getLogger(__name__)

# Bump when the PWA shell (manifest, icons, service worker) changes so clients
# fetch a fresh service worker and drop their old caches.
PWA_VERSION = "1"


def init_app(app):
    oauth.init_app(app)
    oauth.register(
        "google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email"},
    )


def _allowed(email):
    return email is not None and email.lower() in current_app.config["ALLOWED_EMAILS"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _allowed(session.get("email")):
            session.clear()
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)

    return wrapped


def _csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _check_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400)


@bp.get("/login")
def login():
    # scheme comes from the request (ProxyFix maps X-Forwarded-Proto behind Traefik)
    redirect_uri = url_for("admin.auth_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.get("/auth/callback")
def auth_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    if not userinfo.get("email_verified") or not _allowed(email):
        session.clear()
        return render_template("forbidden.html"), 403
    session.clear()
    session["email"] = email.lower()
    return redirect(url_for("admin.panel"))


def _public_link_url(token):
    return url_for("public.confirm", token=token, _external=True)


def _render_panel(new_link_url=None, links_open=False):
    return render_template(
        "panel.html",
        links=db.list_active_links(get_conn()),
        csrf_token=_csrf_token(),
        new_link_url=new_link_url,
        links_open=links_open,
    )


@bp.get("/", strict_slashes=False)
@login_required
def panel():
    return _render_panel()


@bp.post("/links")
@login_required
def create_link():
    _check_csrf()
    minutes = request.form.get("minutes", type=int)
    if minutes is None:
        amount = request.form.get("amount", type=int)
        unit = request.form.get("unit", "hours")
        if amount is None or amount < 1 or unit not in ("minutes", "hours"):
            abort(400)
        minutes = amount if unit == "minutes" else amount * 60
    if minutes < 1:
        abort(400)
    link = db.create_link(get_conn(), duration_minutes=minutes, label=None)
    url = _public_link_url(link["token"])
    return _render_panel(new_link_url=url)


@bp.post("/links/<int:link_id>/revoke")
@login_required
def revoke_link(link_id):
    _check_csrf()
    db.revoke_link(get_conn(), link_id)
    return _render_panel(links_open=True)


# --- PWA: manifest, service worker, offline shell ---------------------------
# These are intentionally unauthenticated so the browser (and the installed
# app) can fetch them before or without an admin session.


@bp.get("/manifest.webmanifest")
def manifest():
    resp = make_response(render_template("manifest.json"))
    resp.mimetype = "application/manifest+json"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/sw.js")
def service_worker():
    resp = make_response(
        render_template(
            "sw.js",
            sw_version=PWA_VERSION,
            static_prefix=url_for("static", filename="").rstrip("/") + "/",
        )
    )
    resp.mimetype = "text/javascript"
    # Let the worker control the whole /admin/ scope and never let a stale copy
    # of the worker script itself be served from HTTP cache.
    resp.headers["Service-Worker-Allowed"] = "/admin/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/offline")
def offline():
    return render_template("offline.html")


@bp.post("/open")
@login_required
def open_gate():
    _check_csrf()
    try:
        current_app.config["GATE_OPENER"]()
    except Exception:
        log.exception("Home Assistant gate call failed")
        return "", 500
    return "", 204

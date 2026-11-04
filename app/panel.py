"""The members' panel at the site root: login, open gate, links, members, activity.

Roles:
  admin    - emails in ALLOWED_EMAILS (env). Everything, plus managing members
             and viewing the activity log.
  resident - added by an admin. Opens the gate and creates links up to 24h.
  guest    - added by an admin. Opens the gate only.
"""

import hmac
import logging
import re
import secrets
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import db, get_conn

bp = Blueprint("panel", __name__)
oauth = OAuth()
log = logging.getLogger(__name__)

# Bump when the PWA shell (manifest, icons, service worker) changes so clients
# fetch a fresh service worker and drop their old caches.
PWA_VERSION = "2"

ADMIN = "admin"
RESIDENT = "resident"
GUEST = "guest"
ALL_ROLES = (ADMIN, RESIDENT, GUEST)

# Residents can create links up to this long; admins are not capped.
RESIDENT_MAX_MINUTES = 24 * 60

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def init_app(app):
    oauth.init_app(app)
    oauth.register(
        "google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email"},
    )


def _admin_emails():
    return current_app.config["ALLOWED_EMAILS"]


def role_for(email):
    """The role for an email, or None if it may not log in. Looked up on every
    request, so removing a member locks them out immediately."""
    if not email:
        return None
    email = email.lower()
    if email in _admin_emails():
        return ADMIN
    return db.get_member_role(get_conn(), email)


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            email = session.get("email")
            role = role_for(email)
            if role is None:
                session.clear()
                return redirect(url_for("panel.login"))
            if role not in roles:
                abort(403)
            g.email = email
            g.role = role
            return view(*args, **kwargs)

        return wrapped

    return decorator


def _csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _check_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400)


# --- auth ----------------------------------------------------------------------


@bp.get("/login")
def login():
    # scheme comes from the request (ProxyFix maps X-Forwarded-Proto behind Traefik)
    redirect_uri = url_for("panel.auth_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@bp.get("/auth/callback")
def auth_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")
    if not userinfo.get("email_verified") or role_for(email) is None:
        session.clear()
        return render_template("forbidden.html"), 403
    session.clear()
    session.permanent = True
    session["email"] = email.lower()
    return redirect(url_for("panel.home"))


@bp.post("/logout")
def logout():
    _check_csrf()
    session.clear()
    return render_template("logged_out.html")


# --- panel ---------------------------------------------------------------------


def _public_link_url(token):
    return url_for("public.confirm", token=token, _external=True)


def _render_panel(new_link_url=None, open_section=None):
    conn = get_conn()
    is_admin = g.role == ADMIN
    ctx = {
        "email": g.email,
        "role": g.role,
        "csrf_token": _csrf_token(),
        "new_link_url": new_link_url,
        "open_section": open_section,
        "can_create_links": g.role in (ADMIN, RESIDENT),
        "is_admin": is_admin,
        "max_hours": 24,
    }
    if ctx["can_create_links"]:
        ctx["links"] = db.list_active_links(conn, created_by=None if is_admin else g.email)
    if is_admin:
        ctx["admins"] = sorted(_admin_emails())
        ctx["members"] = db.list_members(conn)
        ctx["activity"] = db.list_activity(conn)
    return render_template("panel.html", **ctx)


@bp.get("/")
@role_required(*ALL_ROLES)
def home():
    return _render_panel()


@bp.post("/open")
@role_required(*ALL_ROLES)
def open_gate():
    _check_csrf()
    conn = get_conn()
    try:
        current_app.config["GATE_OPENER"]()
    except Exception:
        log.exception("Home Assistant gate call failed")
        db.log_activity(conn, g.email, "gate_open", detail="failed")
        return "", 500
    db.log_activity(conn, g.email, "gate_open")
    return "", 204


@bp.post("/links")
@role_required(ADMIN, RESIDENT)
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
    if g.role == RESIDENT and minutes > RESIDENT_MAX_MINUTES:
        abort(400)
    conn = get_conn()
    link = db.create_link(conn, duration_minutes=minutes, label=None, created_by=g.email)
    db.log_activity(conn, g.email, "link_create", link_id=link["id"], detail=_duration(minutes))
    return _render_panel(new_link_url=_public_link_url(link["token"]))


@bp.post("/links/<int:link_id>/revoke")
@role_required(ADMIN, RESIDENT)
def revoke_link(link_id):
    _check_csrf()
    conn = get_conn()
    owner = None if g.role == ADMIN else g.email
    if db.revoke_link(conn, link_id, created_by=owner):
        db.log_activity(conn, g.email, "link_revoke", link_id=link_id)
    return _render_panel(open_section="links")


@bp.post("/members")
@role_required(ADMIN)
def add_member():
    _check_csrf()
    email = (request.form.get("email") or "").strip().lower()
    role = request.form.get("role")
    if not _EMAIL_RE.match(email) or role not in db.MEMBER_ROLES:
        abort(400)
    if email in _admin_emails():
        abort(400)  # admins are managed through ALLOWED_EMAILS only
    conn = get_conn()
    db.add_member(conn, email, role, added_by=g.email)
    db.log_activity(conn, g.email, "member_add", detail=f"{email} ({role})")
    return _render_panel(open_section="members")


@bp.post("/members/remove")
@role_required(ADMIN)
def remove_member():
    _check_csrf()
    email = (request.form.get("email") or "").strip().lower()
    conn = get_conn()
    if db.remove_member(conn, email):
        db.log_activity(conn, g.email, "member_remove", detail=email)
    return _render_panel(open_section="members")


def _duration(minutes):
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour" + ("" if hours == 1 else "s")
    return f"{minutes} min"


# --- old /admin URLs -------------------------------------------------------------
# The panel used to live under /admin/. Send bookmarks and the old installed PWA
# to the root. Relative Location, so a misdetected scheme can't break it.


@bp.get("/admin", defaults={"rest": ""}, strict_slashes=False)
@bp.get("/admin/<path:rest>")
def old_admin(rest):
    resp = redirect("/", code=302)
    resp.autocorrect_location_header = False
    return resp


@bp.get("/admin/sw.js")
def old_service_worker():
    # The browser re-checks the worker it registered at /admin/sw.js and won't
    # follow a redirect for it, so serve a worker that removes itself.
    resp = make_response(render_template("sw_unregister.js"))
    resp.mimetype = "text/javascript"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# --- PWA: manifest, service worker, offline shell ------------------------------
# These are intentionally unauthenticated so the browser (and the installed
# app) can fetch them before or without a session.


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
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.get("/offline")
def offline():
    return render_template("offline.html")

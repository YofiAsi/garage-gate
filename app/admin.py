import hmac
import secrets
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import db, get_conn

bp = Blueprint("admin", __name__)
oauth = OAuth()


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
    redirect_uri = url_for("admin.auth_callback", _external=True, _scheme="https")
    if current_app.config.get("TESTING"):
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


def _render_panel(new_link_url=None):
    return render_template(
        "panel.html",
        links=db.list_active_links(get_conn()),
        public_host=current_app.config["PUBLIC_HOST"],
        csrf_token=_csrf_token(),
        new_link_url=new_link_url,
    )


@bp.get("/")
@login_required
def panel():
    return _render_panel()


@bp.post("/links")
@login_required
def create_link():
    _check_csrf()
    amount = request.form.get("amount", type=int)
    unit = request.form.get("unit", "hours")
    if amount is None or amount < 1 or unit not in ("minutes", "hours"):
        abort(400)
    minutes = amount if unit == "minutes" else amount * 60
    label = request.form.get("label", "").strip() or None
    link = db.create_link(get_conn(), duration_minutes=minutes, label=label)
    url = f"https://{current_app.config['PUBLIC_HOST']}/{link['token']}"
    return _render_panel(new_link_url=url)


@bp.post("/links/<int:link_id>/revoke")
@login_required
def revoke_link(link_id):
    _check_csrf()
    db.revoke_link(get_conn(), link_id)
    return redirect(url_for("admin.panel"))

import json
import os
from datetime import timedelta

from flask import Flask, g

from app import db


def _cloudflare_scheme_fix(wsgi_app):
    """Trust Cloudflare's own CF-Visitor header for the original scheme.

    Cloudflare (including Cloudflare Tunnel) sets this reliably at its edge.
    An intermediate reverse proxy (e.g. Traefik behind cloudflared) can lose
    or overwrite X-Forwarded-Proto, so this is checked *after* ProxyFix and
    wins when present.
    """

    def middleware(environ, start_response):
        visitor = environ.get("HTTP_CF_VISITOR")
        if visitor:
            try:
                scheme = json.loads(visitor).get("scheme")
            except (ValueError, AttributeError):
                scheme = None
            if scheme in ("http", "https"):
                environ["wsgi.url_scheme"] = scheme
        return wsgi_app(environ, start_response)

    return middleware


def _config_from_env():
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "DB_PATH": os.environ.get("DB_PATH", "/data/links.db"),
        "PUBLIC_HOST": os.environ.get("PUBLIC_HOST"),
        "ALLOWED_EMAILS": [
            e.strip().lower()
            for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
            if e.strip()
        ],
        "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "HA_WEBHOOK_URL": os.environ.get("HA_WEBHOOK_URL"),
        "INSECURE_HTTP": os.environ.get("INSECURE_HTTP", "").lower() in ("1", "true", "yes"),
    }


def get_conn():
    if "db_conn" not in g:
        from flask import current_app

        g.db_conn = db.connect(current_app.config["DB_PATH"])
    return g.db_conn


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.update(_config_from_env())
    if config_overrides:
        app.config.update(config_overrides)

    app.config["SESSION_COOKIE_SECURE"] = not (
        app.config.get("TESTING") or app.config.get("INSECURE_HTTP")
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Keep admins logged in for a week. Sessions are marked permanent at login
    # (see admin.auth_callback); Flask refreshes the expiry on each request, so
    # the week rolls forward as long as the panel is used.
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

    # Trust the reverse proxy's X-Forwarded-Proto/Host (Traefik in production)
    # so url_for(_external=True) builds https URLs behind SSL termination.
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(_cloudflare_scheme_fix(app.wsgi_app), x_proto=1, x_host=1)

    conn = db.connect(app.config["DB_PATH"])
    db.init_schema(conn)
    conn.close()

    if "GATE_OPENER" not in app.config:
        from app.ha import make_gate_opener

        app.config["GATE_OPENER"] = make_gate_opener(app.config)

    @app.teardown_appcontext
    def close_db(exc):
        conn = g.pop("db_conn", None)
        if conn is not None:
            conn.close()

    from app import admin
    from app.public import bp as public_bp

    admin.init_app(app)
    app.register_blueprint(admin.bp, url_prefix="/admin")
    app.register_blueprint(public_bp)

    return app

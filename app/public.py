import logging

from flask import Blueprint, current_app, render_template

from app import db, get_conn

bp = Blueprint("public", __name__)
log = logging.getLogger(__name__)


def _invalid():
    return render_template("invalid.html"), 404


@bp.get("/<token>")
def confirm(token):
    if not db.is_link_valid(get_conn(), token):
        return _invalid()
    return render_template("confirm.html", token=token)


@bp.post("/<token>/open")
def open_gate(token):
    conn = get_conn()
    link = db.use_link(conn, token)
    if link is None:
        return _invalid()
    # Shared-link opens are attributed to whoever created the link.
    try:
        current_app.config["GATE_OPENER"]()
    except Exception:
        log.exception("Home Assistant gate call failed")
        db.log_activity(conn, link["created_by"], "link_open", link_id=link["id"], detail="failed")
        return render_template("error.html"), 500
    db.log_activity(conn, link["created_by"], "link_open", link_id=link["id"])
    return render_template("opening.html")

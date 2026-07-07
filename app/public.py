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
    if not db.use_link(get_conn(), token):
        return _invalid()
    try:
        current_app.config["GATE_OPENER"]()
    except Exception:
        log.exception("Home Assistant gate call failed")
        return render_template("error.html"), 500
    return render_template("opening.html")

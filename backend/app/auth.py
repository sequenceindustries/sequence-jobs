"""Auth blueprint + decorators. Session cookie (HttpOnly, SameSite=Lax, Secure in production) and CSRF token."""
from __future__ import annotations

import hmac
import secrets
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, session

from .services import accounts

bp = Blueprint("auth", __name__)

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def db_url() -> str:
    return current_app.config["DB_URL"]


def client_ip() -> str:
    # Behind Railway's proxy set TRUST_PROXY=1 so the real client IP (first X-Forwarded-For) is used.
    if current_app.config["CFG"].TRUST_PROXY:
        return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()) or request.remote_addr or "?"
    return request.remote_addr or "?"


def current_user():
    if "user" not in g:
        g.user = None
        uid = session.get("uid")
        if uid:
            g.user = accounts.get_user(db_url(), uid)
            if g.user is None:
                session.clear()
    return g.user


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return jsonify(error="auth_required"), 401
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        u = current_user()
        if not u:
            return jsonify(error="auth_required"), 401
        if u["role"] != "admin":
            return jsonify(error="forbidden"), 403
        return fn(*a, **kw)
    return wrapper


def csrf_guard():
    """Registered as before_request on the app: every unsafe API call needs the session's CSRF token."""
    if request.method in UNSAFE and request.path.startswith("/api/"):
        sent = request.headers.get("X-CSRF-Token", "")
        expected = session.get("csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            return jsonify(error="csrf_failed"), 403


def limited(key_prefix: str, limit: int, window_secs: int, by_user: bool = False):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            who = f"u{current_user()['id']}" if by_user and current_user() else client_ip()
            if not accounts.rate_limit_hit(db_url(), f"{key_prefix}:{who}", limit, window_secs):
                return jsonify(error="rate_limited", message="Too many requests. Try again later."), 429
            return fn(*a, **kw)
        return wrapper
    return deco


@bp.get("/csrf")
def csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return jsonify(csrf_token=session["csrf"])


@bp.post("/register")
@limited("register", 10, 3600)
def register():
    body = request.get_json(silent=True) or {}
    try:
        uid = accounts.create_user(db_url(), body.get("email", ""), body.get("password", ""))
    except accounts.AccountError as e:
        return jsonify(error=e.code, message=e.message), (409 if e.code == "email_taken" else 400)
    session.clear()
    session["uid"], session["csrf"] = uid, secrets.token_urlsafe(32)
    session.permanent = True
    return jsonify(id=uid, csrf_token=session["csrf"]), 201


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()[:254]
    # Throttle by IP and by target account so neither guessing many passwords nor many accounts is cheap.
    ok_ip = accounts.rate_limit_hit(db_url(), f"login-ip:{client_ip()}", 30, 900)
    ok_acct = accounts.rate_limit_hit(db_url(), f"login-acct:{email}", 8, 900)
    if not (ok_ip and ok_acct):
        return jsonify(error="rate_limited", message="Too many attempts. Try again in 15 minutes."), 429
    user = accounts.authenticate(db_url(), email, body.get("password", ""))
    if not user:
        accounts.audit(db_url(), None, "login_failed", target=email[:80])
        return jsonify(error="invalid_credentials", message="Email or password is incorrect."), 401
    session.clear()                                   # new session on login (prevents fixation)
    session["uid"], session["csrf"] = user["id"], secrets.token_urlsafe(32)
    session.permanent = True
    if user["role"] == "admin":
        accounts.audit(db_url(), user["id"], "admin_login")
    return jsonify(id=user["id"], email=user["email"], role=user["role"], csrf_token=session["csrf"])


@bp.post("/logout")
def logout():
    session.clear()
    session["csrf"] = secrets.token_urlsafe(32)       # fresh anonymous session so the client can log in again
    return jsonify(ok=True, csrf_token=session["csrf"])


@bp.get("/me")
def me():
    u = current_user()
    if not u:
        return jsonify(user=None)
    return jsonify(user={"id": u["id"], "email": u["email"], "role": u["role"]})


@bp.delete("/account")
@login_required
def delete_account():
    uid = current_user()["id"]
    accounts.delete_user(db_url(), uid)
    session.clear()
    return jsonify(ok=True, deleted=True)

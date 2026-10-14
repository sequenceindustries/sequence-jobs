from flask import Flask, jsonify, request

from .config import Config
from .db import connect


def create_app(config: type[Config] | None = None, ai_gateway=None) -> Flask:
    cfg = config or Config
    app = Flask(__name__)
    app.config["CFG"] = cfg
    app.config["DB_URL"] = cfg.DATABASE_URL
    if cfg.is_production() and not cfg.SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set in production")
    import secrets as _s
    from datetime import timedelta
    app.secret_key = cfg.SECRET_KEY or _s.token_hex(32)     # dev: random per process
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=cfg.is_production(),
                      PERMANENT_SESSION_LIFETIME=timedelta(days=cfg.SESSION_DAYS),
                      MAX_CONTENT_LENGTH=cfg.CV_MAX_BYTES + 4096)

    from .ai.provider import AIGateway
    app.config["AI"] = ai_gateway or AIGateway(
        cfg.DATABASE_URL, None, cfg.AI_DAILY_BUDGET_USD, cfg.AI_MAX_INPUT_TOKENS, cfg.AI_MAX_OUTPUT_TOKENS)

    from .api import bp
    from .auth import bp as auth_bp, csrf_guard
    app.register_blueprint(bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    from .api_user import bp as user_bp
    app.register_blueprint(user_bp, url_prefix="/api")
    from .api_ai import bp as ai_bp
    app.register_blueprint(ai_bp, url_prefix="/api")
    from .api_admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.before_request(csrf_guard)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.errorhandler(413)
    def too_big(_e):
        return jsonify(error="file_too_large"), 413

    @app.errorhandler(404)
    def nf(_e):
        return jsonify(error="not_found"), 404

    return app

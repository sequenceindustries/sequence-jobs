from flask import Flask, jsonify, request

from .config import Config
from .db import connect


def create_app(config: type[Config] | None = None, ai_gateway=None) -> Flask:
    cfg = config or Config
    app = Flask(__name__)
    app.config["CFG"] = cfg
    app.config["DB_URL"] = cfg.DATABASE_URL

    from .ai.provider import AIGateway
    app.config["AI"] = ai_gateway or AIGateway(
        cfg.DATABASE_URL, None, cfg.AI_DAILY_BUDGET_USD, cfg.AI_MAX_INPUT_TOKENS, cfg.AI_MAX_OUTPUT_TOKENS)

    from .api import bp
    app.register_blueprint(bp, url_prefix="/api")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.errorhandler(404)
    def nf(_e):
        return jsonify(error="not_found"), 404

    return app

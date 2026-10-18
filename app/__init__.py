"""Application factory for the inventory admin portal."""
from flask import Flask, jsonify

from . import off_client


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(config or {})

    from .routes import api
    app.register_blueprint(api)

    # Return JSON (not HTML) for every error so the CLI can read the message.
    @app.errorhandler(off_client.ExternalAPIError)
    def external_failure(exc):
        return jsonify({"error": str(exc)}), 502

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"error": "Internal server error."}), 500

    return app

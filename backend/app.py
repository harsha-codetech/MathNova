"""Flask entrypoint.

Run with:  python app.py     (from the backend/ directory)

There is no migration tooling by design -- `db.create_all()` on startup is
enough for a one-day build. `python seed.py` drops and rebuilds the demo data.
"""

from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from models import db
from routes import register_blueprints


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    # The Vite dev server runs on a different origin; this is a local demo so
    # we allow any origin rather than maintaining an allowlist.
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    db.init_app(app)
    register_blueprints(app)

    with app.app_context():
        db.create_all()

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(500)
    def server_error(_e):
        return jsonify({"error": "internal server error"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

"""Blueprint registry.

Blueprints are added phase by phase; each import is deliberately explicit so a
reader can see exactly which surface area exists.
"""


def register_blueprints(app):
    from routes.access import bp as access_bp
    from routes.audit_routes import bp as audit_bp
    from routes.delegates import bp as delegates_bp
    from routes.patients import bp as patients_bp
    from routes.wallet import bp as wallet_bp

    app.register_blueprint(patients_bp)
    app.register_blueprint(access_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(delegates_bp)
    app.register_blueprint(wallet_bp)

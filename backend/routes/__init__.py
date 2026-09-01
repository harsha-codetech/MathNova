"""Blueprint registry.

Blueprints are added phase by phase; each import is deliberately explicit so a
reader can see exactly which surface area exists.
"""


def register_blueprints(app):
    from routes.patients import bp as patients_bp

    app.register_blueprint(patients_bp)

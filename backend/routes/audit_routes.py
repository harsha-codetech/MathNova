"""Audit log endpoints."""

from flask import Blueprint, jsonify

import audit
from models import AuditLogEntry, Patient, db

bp = Blueprint("audit", __name__, url_prefix="/api")


@bp.get("/patients/<int:patient_id>/audit-log")
def get_audit_log(patient_id):
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": "patient not found"}), 404

    entries = (
        AuditLogEntry.query.filter_by(patient_id=patient_id)
        .order_by(AuditLogEntry.id)
        .all()
    )

    return jsonify(
        {
            "patient_id": patient_id,
            # Recomputed on every read: the UI shows a live "chain intact" pill,
            # and it will go red if anyone edits a row directly in SQLite.
            "chain": audit.verify_chain(patient_id),
            "entries": [e.to_dict() for e in entries],
        }
    )

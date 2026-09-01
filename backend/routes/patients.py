"""Patient-facing endpoints: identity list, vault, record creation."""

from flask import Blueprint, current_app, jsonify, request

from ai.pipeline import analyse_new_record
from models import FraudFlag, MedicalRecord, Patient, SafetyFlag, db

bp = Blueprint("patients", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    # `ai` is reported honestly: without an ANTHROPIC_API_KEY the analysers run
    # their offline heuristics, and the UI says so rather than implying Claude
    # wrote an explanation it did not write.
    live = bool(current_app.config.get("ANTHROPIC_API_KEY"))
    return jsonify(
        {
            "status": "ok",
            "service": "MathNova - Patient-Sovereign Prescription Intelligence Network",
            "patients": Patient.query.count(),
            "records": MedicalRecord.query.count(),
            "ai": {
                "mode": "claude" if live else "offline-fallback",
                "model": current_app.config.get("CLAUDE_MODEL"),
            },
        }
    )


@bp.get("/patients")
def list_patients():
    """Backs the role switcher in the UI. No auth by design (see README)."""
    return jsonify([p.to_dict() for p in Patient.query.order_by(Patient.id).all()])


@bp.get("/patients/<int:patient_id>")
def get_patient(patient_id):
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        return jsonify({"error": "patient not found"}), 404
    return jsonify(patient.to_dict())


@bp.get("/patients/<int:patient_id>/vault")
def get_vault(patient_id):
    """The patient's own view of everything they own. This is the one read path
    that needs no access grant -- the patient is the data owner."""
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        return jsonify({"error": "patient not found"}), 404

    records = (
        MedicalRecord.query.filter_by(patient_id=patient_id)
        .order_by(MedicalRecord.id)
        .all()
    )
    grouped = {"prescription": [], "allergy": [], "diagnostic": [], "report": []}
    for record in records:
        grouped.setdefault(record.record_type, []).append(record.to_dict())

    return jsonify(
        {
            "patient": patient.to_dict(),
            "records": [r.to_dict() for r in records],
            "by_type": grouped,
        }
    )


@bp.post("/patients/<int:patient_id>/records")
def add_record(patient_id):
    """Add a medical record. Used by the seed script and by the demo's
    "new prescription arrives" button.

    A new prescription also runs the two AI analysers before responding, so the
    caller gets the safety and fraud verdicts in the same round trip that
    created the record.
    """
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        return jsonify({"error": "patient not found"}), 404

    body = request.get_json(silent=True) or {}
    record_type = body.get("record_type")
    if record_type not in ("prescription", "allergy", "diagnostic", "report"):
        return jsonify({"error": "record_type must be one of prescription|allergy|diagnostic|report"}), 400

    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "payload must be an object"}), 400

    record = MedicalRecord(patient_id=patient_id, record_type=record_type, payload=payload)
    db.session.add(record)
    db.session.flush()

    analysis = analyse_new_record(record)
    db.session.commit()

    return jsonify({"record": record.to_dict(), **analysis}), 201


@bp.get("/patients/<int:patient_id>/flags")
def get_flags(patient_id):
    """Everything the AI layer has flagged for this patient. Surfaced in the UI
    as coloured badges with the full explanation -- never logged silently."""
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": "patient not found"}), 404

    safety_flags = (
        SafetyFlag.query.filter_by(patient_id=patient_id)
        .order_by(SafetyFlag.id.desc())
        .all()
    )
    fraud_flags = (
        FraudFlag.query.filter_by(patient_id=patient_id)
        .order_by(FraudFlag.id.desc())
        .all()
    )
    return jsonify(
        {
            "patient_id": patient_id,
            "safety_flags": [f.to_dict() for f in safety_flags],
            "fraud_flags": [f.to_dict() for f in fraud_flags],
        }
    )

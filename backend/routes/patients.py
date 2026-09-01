"""Patient-facing endpoints: identity list, vault, record creation."""

from flask import Blueprint, jsonify, request

from models import MedicalRecord, Patient, db

bp = Blueprint("patients", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "MathNova - Patient-Sovereign Prescription Intelligence Network",
            "patients": Patient.query.count(),
            "records": MedicalRecord.query.count(),
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

    From phase 5 onward this also triggers the Claude safety check and the
    rule-based fraud heuristics; that wiring lives in routes/insights.py.
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
    db.session.commit()

    return jsonify({"record": record.to_dict()}), 201

"""Glue: run the analysers and write their findings into the audit chain.

Flags are not logged silently -- every one of them appends a `safety_flag` or
`fraud_flag` entry to the patient's hash-chained audit log, so an AI finding is
as tamper-evident as a consent decision.
"""

import audit
from ai import fraud, safety


def _log_flags(patient_id, rows, action, actor, timestamp=None):
    for row in rows:
        audit.log(
            patient_id=patient_id,
            actor=actor,
            action=action,
            timestamp=timestamp,
            details={
                "flag_id": row.id,
                "flag_type": row.flag_type,
                "severity": row.severity,
                "explanation": row.explanation,
                "source": row.source,
                "record_id": getattr(row, "record_id", None),
                "access_request_id": getattr(row, "access_request_id", None),
            },
        )


def analyse_new_record(record, timestamp=None):
    """Safety check + fraud check for a newly created record. Caller commits.

    `timestamp` exists only for the seed script, which backdates history."""
    safety_rows, safety_meta = safety.check_prescription(record)
    fraud_rows, fraud_meta = fraud.check_prescription(record)

    _log_flags(
        record.patient_id, safety_rows, "safety_flag",
        f"MathNova safety analyser ({safety_meta.get('source')})", timestamp,
    )
    _log_flags(
        record.patient_id, fraud_rows, "fraud_flag",
        f"MathNova fraud analyser ({fraud_meta.get('source')})", timestamp,
    )

    return {
        "safety_flags": [r.to_dict() for r in safety_rows],
        "fraud_flags": [r.to_dict() for r in fraud_rows],
        "safety_meta": safety_meta,
        "fraud_meta": fraud_meta,
    }


def analyse_access_request(access_request):
    """Fraud check on the consent side. Caller commits."""
    rows, meta = fraud.check_access_request(access_request)
    _log_flags(
        access_request.patient_id, rows, "fraud_flag",
        f"MathNova fraud analyser ({meta.get('source')})",
    )
    return {"fraud_flags": [r.to_dict() for r in rows], "fraud_meta": meta}

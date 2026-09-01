"""Audit log endpoints."""

from flask import Blueprint, jsonify

import audit
from models import AccessGrant, AccessRequest, AuditLogEntry, Patient, db, iso

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


@bp.get("/patients/<int:patient_id>/disclosure-dashboard")
def disclosure_dashboard(patient_id):
    """"Who has seen my data, when, and why" -- the question the patient
    actually cares about.

    Built entirely from the hash-chained audit log rather than from a separate
    analytics table, so the dashboard cannot disagree with the tamper-evident
    record it summarises.
    """
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": "patient not found"}), 404

    entries = (
        AuditLogEntry.query.filter_by(patient_id=patient_id)
        .order_by(AuditLogEntry.id)
        .all()
    )
    requests = {r.id: r for r in AccessRequest.query.filter_by(patient_id=patient_id).all()}
    grants = {g.id: g for g in AccessGrant.query.filter_by(patient_id=patient_id).all()}

    def requester_for(entry):
        """Resolve the organisation an entry belongs to, or None for patient-side
        actions (approvals, delegate changes) which have no requester."""
        details = entry.details or {}
        request_id = details.get("access_request_id")
        if request_id and request_id in requests:
            return requests[request_id]
        grant_id = details.get("access_grant_id")
        if grant_id and grant_id in grants:
            return requests.get(grants[grant_id].access_request_id)
        return None

    by_requester = {}
    timeline = []

    for entry in entries:
        source = requester_for(entry)
        if source is None:
            continue

        key = source.requester_name
        bucket = by_requester.setdefault(
            key,
            {
                "requester_name": source.requester_name,
                "requester_type": source.requester_type,
                "requests": 0,
                "approvals": 0,
                "denials": 0,
                "reads_allowed": 0,
                "reads_blocked": 0,
                "revocations": 0,
                "fields_seen": [],
                "purposes": [],
                "first_seen": iso(entry.timestamp),
                "last_seen": iso(entry.timestamp),
                "active_grants": 0,
            },
        )
        bucket["last_seen"] = iso(entry.timestamp)

        details = entry.details or {}
        if entry.action == "request_created":
            bucket["requests"] += 1
        elif entry.action in ("approved_by_patient", "approved_by_delegate"):
            bucket["approvals"] += 1
        elif entry.action == "denied":
            bucket["denials"] += 1
        elif entry.action == "grant_revoked":
            bucket["revocations"] += 1
        elif entry.action == "data_accessed":
            if details.get("outcome") == "ALLOWED":
                bucket["reads_allowed"] += 1
                for field in details.get("fields", []):
                    if field not in bucket["fields_seen"]:
                        bucket["fields_seen"].append(field)
            else:
                bucket["reads_blocked"] += 1

        if source.purpose not in bucket["purposes"]:
            bucket["purposes"].append(source.purpose)

        timeline.append(
            {
                "entry_id": entry.id,
                "timestamp": iso(entry.timestamp),
                "requester_name": source.requester_name,
                "requester_type": source.requester_type,
                "actor": entry.actor,
                "action": entry.action,
                "outcome": details.get("outcome"),
                "fields": details.get("fields") or details.get("granted_fields")
                or details.get("requested_fields") or details.get("revoked_scope") or [],
                "purpose": source.purpose,
                "entry_hash": entry.entry_hash,
            }
        )

    for grant in grants.values():
        if grant.effective_status() != "active":
            continue
        source = requests.get(grant.access_request_id)
        if source and source.requester_name in by_requester:
            by_requester[source.requester_name]["active_grants"] += 1

    requesters = sorted(by_requester.values(), key=lambda r: r["last_seen"], reverse=True)

    return jsonify(
        {
            "patient_id": patient_id,
            "chain": audit.verify_chain(patient_id),
            "totals": {
                "requesters": len(requesters),
                "requests": sum(r["requests"] for r in requesters),
                "reads_allowed": sum(r["reads_allowed"] for r in requesters),
                "reads_blocked": sum(r["reads_blocked"] for r in requesters),
                "active_grants": sum(r["active_grants"] for r in requesters),
                "revocations": sum(r["revocations"] for r in requesters),
            },
            "requesters": requesters,
            "timeline": sorted(timeline, key=lambda t: t["timestamp"], reverse=True),
        }
    )

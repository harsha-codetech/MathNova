"""Data model for the Patient-Sovereign Prescription Intelligence Network.

DEMO SIMPLIFICATION (also called out in the README): both the patient's and the
delegate's Ed25519 *private* keys are stored server-side. A real deployment
would keep the private key exclusively client-side (browser keystore, mobile
secure element or a hardware wallet) and the server would only ever hold the
public key. Everything else about the crypto flow -- canonical payloads,
detached Ed25519 signatures, server-side verification against a stored public
key -- is exactly what a production system does.
"""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    """Timezone-aware UTC now (datetime.utcnow() is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


def iso(dt):
    """Serialise a datetime to ISO-8601 with an explicit UTC offset."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------
class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    public_key = db.Column(db.String(64), nullable=False)   # hex-encoded Ed25519 verify key
    private_key = db.Column(db.String(64), nullable=False)  # hex-encoded Ed25519 seed (demo only)

    records = db.relationship("MedicalRecord", backref="patient", lazy="select")
    delegates = db.relationship("Delegate", backref="patient", lazy="select")

    def to_dict(self, include_private=False):
        data = {
            "id": self.id,
            "name": self.name,
            "public_key": self.public_key,
        }
        # The frontend needs the seed only because this demo performs the
        # "wallet" signing step on the server. Never expose this in production.
        if include_private:
            data["private_key"] = self.private_key
        return data


class Delegate(db.Model):
    """A person the patient has authorised to approve access on their behalf
    (spouse, adult child, caregiver). Delegates hold their own keypair, so an
    approval is attributable to the delegate rather than being
    indistinguishable from the patient's own signature."""

    __tablename__ = "delegates"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    delegate_name = db.Column(db.String(120), nullable=False)
    relationship = db.Column(db.String(80), nullable=False)
    delegate_public_key = db.Column(db.String(64), nullable=False)
    delegate_private_key = db.Column(db.String(64), nullable=False)  # demo only
    status = db.Column(db.String(20), nullable=False, default="active")  # active | revoked
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self, include_private=False):
        data = {
            "id": self.id,
            "patient_id": self.patient_id,
            "delegate_name": self.delegate_name,
            "relationship": self.relationship,
            "delegate_public_key": self.delegate_public_key,
            "status": self.status,
            "created_at": iso(self.created_at),
        }
        if include_private:
            data["delegate_private_key"] = self.delegate_private_key
        return data


# --------------------------------------------------------------------------
# Health data
# --------------------------------------------------------------------------
RECORD_TYPES = ("prescription", "allergy", "diagnostic", "report")


class MedicalRecord(db.Model):
    __tablename__ = "medical_records"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    record_type = db.Column(db.String(30), nullable=False)
    # payload keys: drug_name, dosage, frequency, prescriber_name, prescriber_id,
    # date, notes (plus quantity / supply_days, used by the fraud heuristics)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "record_type": self.record_type,
            "payload": self.payload or {},
            "created_at": iso(self.created_at),
        }


# --------------------------------------------------------------------------
# Consent: requests and cryptographically signed grants
# --------------------------------------------------------------------------
REQUESTER_TYPES = ("hospital", "pharmacy", "lab", "insurer")


class AccessRequest(db.Model):
    __tablename__ = "access_requests"

    id = db.Column(db.Integer, primary_key=True)
    requester_name = db.Column(db.String(160), nullable=False)
    requester_type = db.Column(db.String(30), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    requested_fields = db.Column(db.JSON, nullable=False, default=list)
    purpose = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | approved | denied
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    grants = db.relationship("AccessGrant", backref="access_request", lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "requester_name": self.requester_name,
            "requester_type": self.requester_type,
            "patient_id": self.patient_id,
            "requested_fields": self.requested_fields or [],
            "purpose": self.purpose,
            "status": self.status,
            "created_at": iso(self.created_at),
        }


class AccessGrant(db.Model):
    __tablename__ = "access_grants"

    id = db.Column(db.Integer, primary_key=True)
    access_request_id = db.Column(db.Integer, db.ForeignKey("access_requests.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    # "patient" or "delegate:<id>" -- who actually put pen to paper
    granted_by = db.Column(db.String(40), nullable=False)
    signature = db.Column(db.Text, nullable=False)  # hex-encoded Ed25519 detached signature
    scope = db.Column(db.JSON, nullable=False, default=list)
    expires_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")  # active | revoked | expired
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def is_expired(self):
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= utcnow()

    def effective_status(self):
        """`status` is authoritative for revocation; expiry is computed live so a
        grant that simply timed out reads as `expired` without needing a cron
        job to sweep the table."""
        if self.status == "revoked":
            return "revoked"
        return "expired" if self.is_expired() else "active"

    def to_dict(self):
        return {
            "id": self.id,
            "access_request_id": self.access_request_id,
            "patient_id": self.patient_id,
            "granted_by": self.granted_by,
            "signature": self.signature,
            "scope": self.scope or [],
            "expires_at": iso(self.expires_at),
            "status": self.effective_status(),
            "stored_status": self.status,
            "created_at": iso(self.created_at),
        }


# --------------------------------------------------------------------------
# Tamper-evident audit trail
# --------------------------------------------------------------------------
AUDIT_ACTIONS = (
    "request_created",
    "approved_by_patient",
    "approved_by_delegate",
    "denied",
    "data_accessed",
    "grant_revoked",
    "delegate_added",
    "delegate_revoked",
    "safety_flag",
    "fraud_flag",
)


class AuditLogEntry(db.Model):
    """One hash chain per patient. entry_hash = SHA-256 over this entry's fields
    plus prev_entry_hash, so editing any historical row invalidates every hash
    after it -- tamper-evident without a blockchain."""

    __tablename__ = "audit_log_entries"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    actor = db.Column(db.String(160), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    details = db.Column(db.JSON, nullable=False, default=dict)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)
    entry_hash = db.Column(db.String(64), nullable=False)
    prev_entry_hash = db.Column(db.String(64), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "actor": self.actor,
            "action": self.action,
            "details": self.details or {},
            "timestamp": iso(self.timestamp),
            "entry_hash": self.entry_hash,
            "prev_entry_hash": self.prev_entry_hash,
        }


# --------------------------------------------------------------------------
# AI-produced flags
# --------------------------------------------------------------------------
SEVERITIES = ("low", "medium", "high")


class SafetyFlag(db.Model):
    __tablename__ = "safety_flags"

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("medical_records.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    flag_type = db.Column(db.String(60), nullable=False)  # interaction | allergy_conflict | dosage
    severity = db.Column(db.String(10), nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(20), nullable=False, default="claude")  # claude | fallback
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "patient_id": self.patient_id,
            "flag_type": self.flag_type,
            "severity": self.severity,
            "explanation": self.explanation,
            "source": self.source,
            "created_at": iso(self.created_at),
        }


class FraudFlag(db.Model):
    __tablename__ = "fraud_flags"

    id = db.Column(db.Integer, primary_key=True)
    # Exactly one of these is set, depending on what tripped the heuristic.
    record_id = db.Column(db.Integer, db.ForeignKey("medical_records.id"), nullable=True)
    access_request_id = db.Column(db.Integer, db.ForeignKey("access_requests.id"), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    flag_type = db.Column(db.String(60), nullable=False)  # early_refill | high_quantity | prescriber_shopping
    severity = db.Column(db.String(10), nullable=False)
    explanation = db.Column(db.Text, nullable=False)
    triggered_rule = db.Column(db.Text, nullable=False, default="")
    source = db.Column(db.String(20), nullable=False, default="claude")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "record_id": self.record_id,
            "access_request_id": self.access_request_id,
            "patient_id": self.patient_id,
            "flag_type": self.flag_type,
            "severity": self.severity,
            "explanation": self.explanation,
            "triggered_rule": self.triggered_rule,
            "source": self.source,
            "created_at": iso(self.created_at),
        }

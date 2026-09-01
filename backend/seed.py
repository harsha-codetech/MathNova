"""Seed the demo database.

Run:  python seed.py      (from the backend/ directory)

Drops every table and rebuilds a deterministic demo world so the app has
something to show on first load without any manual clicking.

The consent history is not faked: every seeded grant is produced by actually
signing the canonical payload with the patient's (or delegate's) Ed25519 key
and verifying it, and every step appends a real hash-chained audit entry. If
the crypto were broken, seeding would fail.

Later phases extend this file:
  * phase 5/6 -- the prescriptions that trip the safety and fraud analysers
"""

from datetime import timedelta

import audit
from access_control import normalise_fields
from app import create_app
from crypto_utils import (
    canonical_json,
    generate_keypair,
    grant_payload,
    revoke_delegate_payload,
    revoke_grant_payload,
    sha256_hex,
    sign_message,
    verify_signature,
)
from models import (
    AccessGrant,
    AccessRequest,
    Delegate,
    MedicalRecord,
    Patient,
    db,
    iso,
    utcnow,
)


def _iso_date(days_ago):
    return (utcnow() - timedelta(days=days_ago)).date().isoformat()


def make_patient(name):
    private_key, public_key = generate_keypair()
    patient = Patient(name=name, public_key=public_key, private_key=private_key)
    db.session.add(patient)
    db.session.flush()  # assign patient.id
    return patient


def make_delegate(patient, delegate_name, relationship, status="active"):
    private_key, public_key = generate_keypair()
    delegate = Delegate(
        patient_id=patient.id,
        delegate_name=delegate_name,
        relationship=relationship,
        delegate_public_key=public_key,
        delegate_private_key=private_key,
        status=status,
    )
    db.session.add(delegate)
    db.session.flush()
    return delegate


def add_record(patient, record_type, payload):
    record = MedicalRecord(patient_id=patient.id, record_type=record_type, payload=payload)
    db.session.add(record)
    db.session.flush()
    return record


def prescription(drug_name, dosage, frequency, prescriber_name, prescriber_id,
                 days_ago, notes="", quantity=30, supply_days=30):
    return {
        "drug_name": drug_name,
        "dosage": dosage,
        "frequency": frequency,
        "prescriber_name": prescriber_name,
        "prescriber_id": prescriber_id,
        "date": _iso_date(days_ago),
        "notes": notes,
        "quantity": quantity,
        "supply_days": supply_days,
    }


# --------------------------------------------------------------------------
# Consent helpers -- these walk the *real* crypto path, no shortcuts
# --------------------------------------------------------------------------
def make_request(patient, requester_name, requester_type, fields, purpose, minutes_ago=0):
    access_request = AccessRequest(
        requester_name=requester_name,
        requester_type=requester_type,
        patient_id=patient.id,
        requested_fields=normalise_fields(fields),
        purpose=purpose,
        status="pending",
        created_at=utcnow() - timedelta(minutes=minutes_ago),
    )
    db.session.add(access_request)
    db.session.flush()
    audit.log(
        patient_id=patient.id,
        actor=f"{requester_name} ({requester_type})",
        action="request_created",
        details={
            "access_request_id": access_request.id,
            "requested_fields": access_request.requested_fields,
            "purpose": purpose,
        },
        timestamp=access_request.created_at,
    )
    return access_request


def approve(access_request, patient, delegate=None, granted_fields=None, valid_days=7):
    """Sign, verify, then grant -- the same sequence the API performs."""
    fields = normalise_fields(granted_fields or access_request.requested_fields)
    expires_at = utcnow() + timedelta(days=valid_days)
    expires_at_iso = iso(expires_at)

    if delegate is None:
        private_key, public_key = patient.private_key, patient.public_key
        granted_by, actor, action = "patient", patient.name, "approved_by_patient"
    else:
        private_key, public_key = delegate.delegate_private_key, delegate.delegate_public_key
        granted_by = f"delegate:{delegate.id}"
        actor = f"{delegate.delegate_name} ({delegate.relationship}, delegate)"
        action = "approved_by_delegate"

    message = canonical_json(grant_payload(access_request.id, fields, expires_at_iso))
    signature = sign_message(private_key, message)
    assert verify_signature(public_key, message, signature), "seed produced an invalid signature"

    grant = AccessGrant(
        access_request_id=access_request.id,
        patient_id=patient.id,
        granted_by=granted_by,
        signature=signature,
        scope=fields,
        expires_at=expires_at,
        status="active",
    )
    access_request.status = "approved"
    db.session.add(grant)
    db.session.flush()

    audit.log(
        patient_id=patient.id,
        actor=actor,
        action=action,
        details={
            "access_request_id": access_request.id,
            "access_grant_id": grant.id,
            "granted_fields": fields,
            "expires_at": expires_at_iso,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
            "verified_against_public_key": public_key,
        },
    )
    return grant


def record_access(grant, access_request, patient, fields=None, minutes_ago=0):
    """Log a read that already happened, so the disclosure dashboard is populated
    on first load."""
    used = fields or grant.scope
    audit.log(
        patient_id=patient.id,
        actor=f"{access_request.requester_name} ({access_request.requester_type})",
        action="data_accessed",
        details={
            "access_grant_id": grant.id,
            "access_request_id": access_request.id,
            "outcome": "ALLOWED",
            "fields": list(used),
            "record_count": MedicalRecord.query.filter(
                MedicalRecord.patient_id == patient.id
            ).count(),
            "purpose": access_request.purpose,
        },
        timestamp=utcnow() - timedelta(minutes=minutes_ago),
    )


def revoke(grant, patient, delegate=None):
    """Sign {grant_id, action:"revoke"}, verify, then flip the grant to revoked."""
    if delegate is None:
        private_key, public_key, actor = patient.private_key, patient.public_key, patient.name
    else:
        private_key = delegate.delegate_private_key
        public_key = delegate.delegate_public_key
        actor = f"{delegate.delegate_name} ({delegate.relationship}, delegate)"

    message = canonical_json(revoke_grant_payload(grant.id))
    signature = sign_message(private_key, message)
    assert verify_signature(public_key, message, signature), "seed produced an invalid signature"

    grant.status = "revoked"
    source = db.session.get(AccessRequest, grant.access_request_id)
    audit.log(
        patient_id=patient.id,
        actor=actor,
        action="grant_revoked",
        details={
            "access_grant_id": grant.id,
            "access_request_id": grant.access_request_id,
            "requester_name": source.requester_name if source else None,
            "revoked_scope": grant.scope,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
            "verified_against_public_key": public_key,
        },
    )
    return grant


def revoke_delegate(delegate, patient):
    message = canonical_json(revoke_delegate_payload(delegate.id))
    signature = sign_message(patient.private_key, message)
    assert verify_signature(patient.public_key, message, signature)

    delegate.status = "revoked"
    audit.log(
        patient_id=patient.id,
        actor=patient.name,
        action="delegate_revoked",
        details={
            "delegate_id": delegate.id,
            "delegate_name": delegate.delegate_name,
            "relationship": delegate.relationship,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
            "verified_against_public_key": patient.public_key,
        },
    )
    return delegate


def log_delegate_added(delegate, patient):
    """Seeded delegates still get a signed, audited appointment entry."""
    from crypto_utils import add_delegate_payload

    message = canonical_json(
        add_delegate_payload(patient.id, delegate.delegate_name, delegate.relationship)
    )
    signature = sign_message(patient.private_key, message)
    assert verify_signature(patient.public_key, message, signature)
    audit.log(
        patient_id=patient.id,
        actor=patient.name,
        action="delegate_added",
        details={
            "delegate_id": delegate.id,
            "delegate_name": delegate.delegate_name,
            "relationship": delegate.relationship,
            "delegate_public_key": delegate.delegate_public_key,
            "signature": signature,
            "signed_message": message,
            "message_sha256": sha256_hex(message),
        },
    )


# --------------------------------------------------------------------------
# The demo world
# --------------------------------------------------------------------------
def seed_people():
    """Three patients, their baseline medication lists, allergies and delegates."""

    # ------------------------------------------------------------------
    # Patient 1 -- stable chronic-care patient, used for the "happy path"
    # ------------------------------------------------------------------
    ananya = make_patient("Ananya Iyer")
    add_record(ananya, "allergy", {
        "drug_name": "Penicillin",
        "notes": "Documented anaphylaxis in 2019. Avoid all beta-lactams.",
        "date": _iso_date(1400),
    })
    add_record(ananya, "prescription", prescription(
        "Metformin", "500 mg", "twice daily", "Dr. Rajesh Menon", "MCI-KA-44120",
        days_ago=95, notes="Type 2 diabetes, stable HbA1c.", quantity=60, supply_days=30))
    add_record(ananya, "prescription", prescription(
        "Amlodipine", "5 mg", "once daily", "Dr. Rajesh Menon", "MCI-KA-44120",
        days_ago=95, notes="Hypertension.", quantity=30, supply_days=30))
    add_record(ananya, "prescription", prescription(
        "Atorvastatin", "10 mg", "once daily at night", "Dr. Rajesh Menon", "MCI-KA-44120",
        days_ago=60, notes="Dyslipidaemia.", quantity=30, supply_days=30))
    add_record(ananya, "diagnostic", {
        "test_name": "HbA1c",
        "result": "6.8%",
        "date": _iso_date(40),
        "notes": "Improved from 7.9% six months ago.",
        "prescriber_name": "Dr. Rajesh Menon",
    })
    sunita = make_delegate(ananya, "Sunita Iyer", "Mother")
    log_delegate_added(sunita, ananya)
    # A delegate who was authorised and later revoked -- proves that delegate
    # authority is itself revocable, not a permanent back door.
    vikram = make_delegate(ananya, "Vikram Iyer", "Brother")
    log_delegate_added(vikram, ananya)
    revoke_delegate(vikram, ananya)

    # ------------------------------------------------------------------
    # Patient 2 -- on warfarin; set up for the phase 5 safety flag
    # (an NSAID on top of warfarin is a genuine major interaction)
    # ------------------------------------------------------------------
    rohit = make_patient("Rohit Deshmukh")
    add_record(rohit, "allergy", {
        "drug_name": "Sulfonamides (sulfa drugs)",
        "notes": "Severe rash and fever after co-trimoxazole, 2021.",
        "date": _iso_date(1000),
    })
    add_record(rohit, "prescription", prescription(
        "Warfarin", "5 mg", "once daily", "Dr. Priya Nair", "MCI-MH-71903",
        days_ago=180, notes="Mechanical mitral valve. Target INR 2.5-3.5.",
        quantity=30, supply_days=30))
    add_record(rohit, "prescription", prescription(
        "Levothyroxine", "50 mcg", "once daily before food", "Dr. Priya Nair", "MCI-MH-71903",
        days_ago=180, notes="Hypothyroidism.", quantity=30, supply_days=30))
    add_record(rohit, "prescription", prescription(
        "Losartan", "50 mg", "once daily", "Dr. Priya Nair", "MCI-MH-71903",
        days_ago=120, notes="Hypertension.", quantity=30, supply_days=30))
    add_record(rohit, "report", {
        "test_name": "INR",
        "result": "2.9",
        "date": _iso_date(12),
        "notes": "Within therapeutic range.",
        "prescriber_name": "Dr. Priya Nair",
    })
    kavita = make_delegate(rohit, "Kavita Deshmukh", "Spouse")
    log_delegate_added(kavita, rohit)

    # ------------------------------------------------------------------
    # Patient 3 -- set up for the phase 5 fraud flag (prescriber shopping on a
    # controlled analgesic) and an NSAID allergy on record
    # ------------------------------------------------------------------
    meera = make_patient("Meera Krishnan")
    add_record(meera, "allergy", {
        "drug_name": "Ibuprofen (NSAIDs)",
        "notes": "Aspirin-exacerbated respiratory disease. Bronchospasm on NSAIDs.",
        "date": _iso_date(800),
    })
    add_record(meera, "prescription", prescription(
        "Salbutamol inhaler", "100 mcg", "2 puffs as needed", "Dr. Arjun Pillai", "MCI-TN-30877",
        days_ago=150, notes="Asthma, rescue inhaler.", quantity=1, supply_days=60))
    add_record(meera, "prescription", prescription(
        "Sertraline", "50 mg", "once daily", "Dr. Arjun Pillai", "MCI-TN-30877",
        days_ago=90, notes="Generalised anxiety disorder.", quantity=30, supply_days=30))

    return {
        "ananya": ananya,
        "rohit": rohit,
        "meera": meera,
        "sunita": sunita,
        "kavita": kavita,
        "vikram": vikram,
    }


def seed_consent(people):
    """Pending requests plus one already-approved-and-used grant, so both the
    approval queue and the disclosure dashboard have content on first load."""
    ananya, rohit, meera = people["ananya"], people["rohit"], people["meera"]
    kavita = people["kavita"]

    # An approved, actively-used grant on Ananya's vault.
    apollo = make_request(
        ananya,
        "Apollo Pharmacy, Indiranagar",
        "pharmacy",
        ["prescriptions", "allergies"],
        "Dispense the monthly Metformin refill and screen it against documented allergies.",
        minutes_ago=2880,
    )
    apollo_grant = approve(apollo, ananya, valid_days=14)
    record_access(apollo_grant, apollo, ananya, minutes_ago=2870)
    record_access(apollo_grant, apollo, ananya, ["prescriptions"], minutes_ago=1400)

    # A full request -> grant -> read -> REVOKE cycle, so the disclosure
    # dashboard shows a completed lifecycle without anyone touching the UI.
    healthfirst = make_request(
        ananya,
        "HealthFirst Clinic, Koramangala",
        "hospital",
        ["prescriptions", "diagnostics"],
        "Second opinion on diabetes management, requested during a walk-in consult.",
        minutes_ago=600,
    )
    healthfirst_grant = approve(healthfirst, ananya, valid_days=30)
    record_access(healthfirst_grant, healthfirst, ananya, minutes_ago=590)
    revoke(healthfirst_grant, ananya)

    # Delegated proxy consent: Rohit was sedated after a procedure, so his
    # spouse Kavita signed with her own key. The audit entry says so.
    wockhardt = make_request(
        rohit,
        "Wockhardt Hospital, Nagpur",
        "hospital",
        ["prescriptions", "allergies"],
        "Emergency admission -- patient sedated, need anticoagulant and allergy status now.",
        minutes_ago=420,
    )
    wockhardt_grant = approve(wockhardt, rohit, delegate=kavita, valid_days=3)
    record_access(wockhardt_grant, wockhardt, rohit, minutes_ago=415)

    # Pending requests -- the patient approval queue.
    make_request(
        rohit,
        "Fortis Hospital, Mulund",
        "hospital",
        ["prescriptions", "allergies", "reports"],
        "Pre-operative anaesthetic assessment ahead of a dental extraction on Friday.",
        minutes_ago=90,
    )
    make_request(
        ananya,
        "MaxLife Insurance",
        "insurer",
        ["diagnostics", "reports"],
        "Adjudicate claim ML-88213 for the September outpatient visit.",
        minutes_ago=45,
    )
    make_request(
        meera,
        "SRL Diagnostics, T. Nagar",
        "lab",
        ["prescriptions"],
        "Confirm current medication list before a scheduled pulmonary function test.",
        minutes_ago=20,
    )

    return {
        "apollo_request": apollo,
        "apollo_grant": apollo_grant,
        "healthfirst_grant": healthfirst_grant,
        "wockhardt_grant": wockhardt_grant,
    }


def run():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        people = seed_people()
        db.session.flush()
        seed_consent(people)
        db.session.commit()

        print("Seeded MathNova demo data")
        for patient in Patient.query.order_by(Patient.id):
            record_count = MedicalRecord.query.filter_by(patient_id=patient.id).count()
            delegate_count = Delegate.query.filter_by(patient_id=patient.id).count()
            chain = audit.verify_chain(patient.id)
            print(
                f"  [{patient.id}] {patient.name:<18} "
                f"records={record_count} delegates={delegate_count} "
                f"audit={chain['length']} chain={'INTACT' if chain['valid'] else 'BROKEN'}"
            )
        print(
            f"  requests={AccessRequest.query.count()} "
            f"grants={AccessGrant.query.count()} "
            f"(revoked={AccessGrant.query.filter_by(status='revoked').count()}) "
            f"delegates={Delegate.query.count()}"
        )


if __name__ == "__main__":
    run()

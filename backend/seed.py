"""Seed the demo database.

Run:  python seed.py      (from the backend/ directory)

Drops every table and rebuilds a deterministic demo world so the app has
something to show on first load without any manual clicking. Later phases
extend this file:
  * phase 2 -- signed grants + a hash-chained audit trail
  * phase 4 -- a full request -> grant -> revoke cycle and a revoked delegate
  * phase 5/6 -- the prescriptions that trip the safety and fraud analysers
"""

from datetime import timedelta

from app import create_app
from crypto_utils import generate_keypair
from models import Delegate, MedicalRecord, Patient, db, utcnow


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
    make_delegate(ananya, "Sunita Iyer", "Mother")

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
    make_delegate(rohit, "Kavita Deshmukh", "Spouse")

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

    return {"ananya": ananya, "rohit": rohit, "meera": meera}


def run():
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        people = seed_people()
        db.session.commit()

        print("Seeded MathNova demo data")
        for key, patient in people.items():
            record_count = MedicalRecord.query.filter_by(patient_id=patient.id).count()
            delegate_count = Delegate.query.filter_by(patient_id=patient.id).count()
            print(
                f"  [{patient.id}] {patient.name:<20} "
                f"records={record_count} delegates={delegate_count} "
                f"pubkey={patient.public_key[:16]}..."
            )


if __name__ == "__main__":
    run()

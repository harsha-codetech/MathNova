"""Prescription safety check -- one Claude call, one job.

Runs whenever a new prescription MedicalRecord is created. Claude is given the
new prescription plus the patient's current medication list and documented
allergies, and asked for interactions, allergy conflicts and dosage concerns in
plain language with a severity rating.

There is NO drug-interaction database here, by design: Claude reasoning over
the patient's own vault is the intended mechanism. The small table at the
bottom of this file is an offline stand-in used only when no API key is present,
so a demo without network access still shows the feature working. Flags it
produces are stored with source="fallback" and the UI labels them as such.
"""

from ai.claude_client import ask_claude, is_live, normalise_flags
from models import MedicalRecord, SafetyFlag, db

ALLOWED_TYPES = ("interaction", "allergy_conflict", "dosage")

SYSTEM_PROMPT = """You are a clinical medication-safety reviewer inside an electronic \
health-record system. You are given ONE new prescription plus the patient's current \
medications and documented allergies.

Identify ONLY concerns that are genuinely supported by the data you are given:
  - "interaction"       : a clinically meaningful interaction with a current medication
  - "allergy_conflict"  : the new drug is, or belongs to the same class as, a documented allergy
  - "dosage"            : the dose, frequency or quantity is outside the usual safe range

Write each explanation in plain language a patient could understand, in one or two \
sentences, naming the specific drugs involved and the actual risk.

Severity: "high" = could cause serious harm and needs prescriber contact before \
dispensing; "medium" = needs monitoring or a dose review; "low" = worth noting.

Respond with STRICT JSON ONLY. No markdown, no code fences, no commentary before or \
after. Exact schema:
{"flags": [{"type": "interaction|allergy_conflict|dosage", "severity": "low|medium|high", \
"explanation": "..."}]}

If nothing is concerning, return exactly {"flags": []}. Do not invent concerns to be \
helpful -- an empty list is a valid and often correct answer."""


def _describe(record):
    p = record.payload or {}
    parts = [p.get("drug_name") or "unnamed drug"]
    if p.get("dosage"):
        parts.append(p["dosage"])
    if p.get("frequency"):
        parts.append(p["frequency"])
    if p.get("quantity"):
        parts.append(f"quantity {p['quantity']}")
    if p.get("supply_days"):
        parts.append(f"{p['supply_days']}-day supply")
    line = " | ".join(str(x) for x in parts)
    if p.get("prescriber_name"):
        line += f" | prescribed by {p['prescriber_name']}"
    if p.get("notes"):
        line += f" | note: {p['notes']}"
    return line


def build_prompt(new_record, current_meds, allergies):
    meds = "\n".join(f"  - {_describe(m)}" for m in current_meds) or "  (none on file)"
    allergy_lines = []
    for a in allergies:
        p = a.payload or {}
        allergy_lines.append(
            f"  - {p.get('drug_name', 'unknown')}"
            + (f" — {p['notes']}" if p.get("notes") else "")
        )
    allergy_text = "\n".join(allergy_lines) or "  (none documented)"

    return (
        f"NEW PRESCRIPTION\n  - {_describe(new_record)}\n\n"
        f"PATIENT'S CURRENT MEDICATIONS\n{meds}\n\n"
        f"DOCUMENTED ALLERGIES\n{allergy_text}\n\n"
        "Review the new prescription against the two lists above."
    )


def check_prescription(record):
    """Analyse a freshly created prescription and persist any SafetyFlag rows.

    Returns (flag_rows, meta) where meta says whether Claude or the offline
    fallback produced the result. Caller commits.
    """
    if record.record_type != "prescription":
        return [], {"source": "skipped", "reason": "not a prescription"}

    others = (
        MedicalRecord.query.filter(
            MedicalRecord.patient_id == record.patient_id,
            MedicalRecord.id != record.id,
        )
        .order_by(MedicalRecord.id)
        .all()
    )
    current_meds = [m for m in others if m.record_type == "prescription"]
    allergies = [m for m in others if m.record_type == "allergy"]

    source = "claude"
    note = None
    flags = []

    if is_live():
        parsed, error = ask_claude(
            SYSTEM_PROMPT, build_prompt(record, current_meds, allergies)
        )
        if error:
            source, note = "fallback", error
            flags = offline_review(record, current_meds, allergies)
        else:
            flags = normalise_flags(parsed, ALLOWED_TYPES, "interaction")
    else:
        source = "fallback"
        note = "no ANTHROPIC_API_KEY configured"
        flags = offline_review(record, current_meds, allergies)

    rows = []
    for flag in flags:
        row = SafetyFlag(
            record_id=record.id,
            patient_id=record.patient_id,
            flag_type=flag["type"],
            severity=flag["severity"],
            explanation=flag["explanation"],
            source=source,
        )
        db.session.add(row)
        rows.append(row)
    db.session.flush()

    return rows, {"source": source, "note": note, "count": len(rows)}


# --------------------------------------------------------------------------
# Offline stand-in (NOT a drug database -- see the module docstring)
# --------------------------------------------------------------------------
DRUG_CLASSES = {
    "nsaid": ["ibuprofen", "naproxen", "diclofenac", "aspirin", "ketorolac", "nsaid"],
    "beta_lactam": ["penicillin", "amoxicillin", "ampicillin", "cefalexin", "cephalexin", "augmentin"],
    "sulfonamide": ["sulfamethoxazole", "co-trimoxazole", "cotrimoxazole", "sulfasalazine", "sulfa"],
    "opioid": ["tramadol", "codeine", "morphine", "oxycodone", "fentanyl"],
    "ssri": ["sertraline", "fluoxetine", "escitalopram", "paroxetine"],
    "anticoagulant": ["warfarin", "acenocoumarol", "apixaban", "rivaroxaban"],
}

INTERACTIONS = [
    ("anticoagulant", "nsaid",
     "Taking an NSAID alongside an anticoagulant markedly raises the risk of "
     "gastrointestinal and other bleeding.", "high"),
    ("anticoagulant", "opioid",
     "Some opioids alter anticoagulant metabolism; INR should be rechecked within a week.",
     "medium"),
    ("ssri", "opioid",
     "An SSRI combined with tramadol or another serotonergic opioid can precipitate "
     "serotonin syndrome.", "high"),
    ("ssri", "nsaid",
     "SSRIs plus NSAIDs increase the risk of gastrointestinal bleeding.", "medium"),
]


def _classes_of(name):
    lowered = (name or "").lower()
    return {cls for cls, members in DRUG_CLASSES.items() if any(m in lowered for m in members)}


def offline_review(record, current_meds, allergies):
    """Deterministic degraded-mode review, used only when Claude is unreachable."""
    payload = record.payload or {}
    new_name = payload.get("drug_name") or ""
    new_classes = _classes_of(new_name)
    flags = []

    for allergy in allergies:
        allergy_name = (allergy.payload or {}).get("drug_name") or ""
        allergy_classes = _classes_of(allergy_name)
        shares_class = bool(new_classes & allergy_classes)
        same_drug = new_name.split()[0].lower() in allergy_name.lower() if new_name else False
        if shares_class or same_drug:
            flags.append({
                "type": "allergy_conflict",
                "severity": "high",
                "explanation": (
                    f"{new_name} conflicts with this patient's documented allergy to "
                    f"{allergy_name}. Do not dispense without prescriber confirmation."
                ),
            })

    for med in current_meds:
        med_name = (med.payload or {}).get("drug_name") or ""
        med_classes = _classes_of(med_name)
        for class_a, class_b, text, severity in INTERACTIONS:
            pair = (
                (class_a in new_classes and class_b in med_classes)
                or (class_b in new_classes and class_a in med_classes)
            )
            if pair:
                flags.append({
                    "type": "interaction",
                    "severity": severity,
                    "explanation": f"{new_name} + {med_name}: {text}",
                })

    quantity = payload.get("quantity")
    supply_days = payload.get("supply_days")
    if isinstance(quantity, int) and isinstance(supply_days, int) and supply_days:
        per_day = quantity / supply_days
        if per_day > 4:
            flags.append({
                "type": "dosage",
                "severity": "medium",
                "explanation": (
                    f"{quantity} units over {supply_days} days works out at roughly "
                    f"{per_day:.1f} doses a day, which is higher than a typical regimen. "
                    "Worth confirming the intended frequency."
                ),
            })

    # De-duplicate identical explanations produced by overlapping rules.
    seen, unique = set(), []
    for flag in flags:
        if flag["explanation"] not in seen:
            seen.add(flag["explanation"])
            unique.append(flag)
    return unique

"""Fraud detection -- rules first, Claude second.

The expensive part (an LLM call) never runs unless a cheap deterministic rule
has already fired. That ordering is the whole design: plain Python decides
*whether* something is suspicious, Claude only explains *why* it looks that way
in language a patient or pharmacist can act on.

Prescription rules (from the brief):
  R1 early_refill        -- a refill arrives less than 80% of the way through the
                            previous supply
  R2 high_quantity       -- quantity is far above the usual range for that drug
  R3 prescriber_shopping -- 3+ distinct prescribers for the same drug within 30
                            days for the same patient

Access-request rules (the brief's three rules are prescription-shaped, so these
are the equivalent heuristics for the consent side -- noted as an extension):
  R4 request_velocity    -- 3+ requests from the same requester for the same
                            patient inside 7 days
  R5 over_collection     -- the entire vault requested for a narrow stated purpose
"""

from datetime import datetime, timedelta, timezone

from ai.claude_client import ask_claude, is_live, normalise_flags
from models import AccessRequest, FraudFlag, MedicalRecord, db, utcnow

ALLOWED_TYPES = (
    "early_refill",
    "high_quantity",
    "prescriber_shopping",
    "request_velocity",
    "over_collection",
)

SYSTEM_PROMPT = """You are a prescription-fraud analyst inside an electronic health-record \
system. A deterministic rule has ALREADY fired -- your job is not to decide whether \
something is suspicious, it is to explain, in plain language, why the pattern you are \
shown looks suspicious and what a pharmacist or patient should do about it.

Be specific: name the drug, the dates, the prescribers or the requester involved. Two or \
three sentences. Do not moralise and do not accuse anyone of a crime -- these patterns \
have innocent explanations too, and you should say so when one is plausible.

Keep the "type" exactly as given to you in TRIGGERED RULE.

Severity: "high" = strongly consistent with diversion or misuse and should block \
dispensing pending review; "medium" = warrants a phone call; "low" = log and watch.

Respond with STRICT JSON ONLY. No markdown, no code fences, no commentary before or \
after. Exact schema:
{"flags": [{"type": "...", "severity": "low|medium|high", "explanation": "..."}]}"""

# A tiny heuristic table, not a drug database: the largest quantity that would
# be unremarkable on a single script. Anything absent uses DEFAULT_MAX_QUANTITY.
TYPICAL_MAX_QUANTITY = {
    "tramadol": 30,
    "codeine": 30,
    "morphine": 30,
    "oxycodone": 30,
    "alprazolam": 30,
    "zolpidem": 30,
    "warfarin": 60,
    "metformin": 90,
}
DEFAULT_MAX_QUANTITY = 120

EARLY_REFILL_THRESHOLD = 0.8  # "less than 80% through the expected supply"
PRESCRIBER_SHOPPING_WINDOW_DAYS = 30
PRESCRIBER_SHOPPING_MIN = 3
REQUEST_VELOCITY_WINDOW_DAYS = 7
REQUEST_VELOCITY_MIN = 3


def _as_utc(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _record_date(record):
    """Prefer the clinical date on the payload, fall back to the row timestamp."""
    return _as_utc((record.payload or {}).get("date")) or _as_utc(record.created_at)


def _same_drug(a, b):
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    return a == b or a.split()[0] == b.split()[0]


# --------------------------------------------------------------------------
# Rule layer -- pure Python, no AI, no network
# --------------------------------------------------------------------------
def evaluate_prescription_rules(record):
    """Return a list of triggered-rule dicts (empty means nothing to explain)."""
    payload = record.payload or {}
    drug = payload.get("drug_name") or ""
    triggered = []

    history = [
        r
        for r in MedicalRecord.query.filter(
            MedicalRecord.patient_id == record.patient_id,
            MedicalRecord.record_type == "prescription",
            MedicalRecord.id != record.id,
        ).all()
        if _same_drug((r.payload or {}).get("drug_name"), drug)
    ]

    new_date = _record_date(record) or utcnow()

    # R1 -- early refill
    previous = [r for r in history if (_record_date(r) or utcnow()) <= new_date]
    if previous:
        latest = max(previous, key=lambda r: _record_date(r) or utcnow())
        latest_date = _record_date(latest)
        supply_days = (latest.payload or {}).get("supply_days")
        if latest_date and isinstance(supply_days, int) and supply_days > 0:
            elapsed = (new_date - latest_date).days
            if 0 <= elapsed < EARLY_REFILL_THRESHOLD * supply_days:
                triggered.append({
                    "type": "early_refill",
                    "severity": "medium",
                    "rule": (
                        f"Refill of {drug} requested {elapsed} days into a "
                        f"{supply_days}-day supply "
                        f"({elapsed / supply_days:.0%} elapsed, threshold 80%)."
                    ),
                    "evidence": {
                        "drug": drug,
                        "days_since_last_fill": elapsed,
                        "previous_supply_days": supply_days,
                        "previous_prescriber": (latest.payload or {}).get("prescriber_name"),
                        "previous_date": (latest.payload or {}).get("date"),
                    },
                })

    # R2 -- unusually high quantity
    quantity = payload.get("quantity")
    if isinstance(quantity, int):
        cap = DEFAULT_MAX_QUANTITY
        for name, limit in TYPICAL_MAX_QUANTITY.items():
            if name in drug.lower():
                cap = limit
                break
        if quantity > cap:
            triggered.append({
                "type": "high_quantity",
                "severity": "medium",
                "rule": (
                    f"Quantity {quantity} for {drug} exceeds the usual maximum of {cap} "
                    "units on a single prescription."
                ),
                "evidence": {"drug": drug, "quantity": quantity, "usual_maximum": cap},
            })

    # R3 -- prescriber shopping
    window_start = new_date - timedelta(days=PRESCRIBER_SHOPPING_WINDOW_DAYS)
    recent = [record] + [
        r for r in history if (_record_date(r) or utcnow()) >= window_start
    ]
    prescribers = {}
    for r in recent:
        name = (r.payload or {}).get("prescriber_name")
        if name:
            prescribers.setdefault(name, (r.payload or {}).get("date"))
    if len(prescribers) >= PRESCRIBER_SHOPPING_MIN:
        triggered.append({
            "type": "prescriber_shopping",
            "severity": "high",
            "rule": (
                f"{len(prescribers)} distinct prescribers wrote {drug} for this patient "
                f"within {PRESCRIBER_SHOPPING_WINDOW_DAYS} days."
            ),
            "evidence": {
                "drug": drug,
                "prescribers": [
                    {"name": name, "date": date} for name, date in prescribers.items()
                ],
                "window_days": PRESCRIBER_SHOPPING_WINDOW_DAYS,
            },
        })

    return triggered


def evaluate_request_rules(access_request):
    triggered = []
    created = _as_utc(access_request.created_at) or utcnow()

    # R4 -- request velocity from one requester against one patient
    window_start = created - timedelta(days=REQUEST_VELOCITY_WINDOW_DAYS)
    siblings = [
        r
        for r in AccessRequest.query.filter(
            AccessRequest.patient_id == access_request.patient_id,
            AccessRequest.requester_name == access_request.requester_name,
        ).all()
        if (_as_utc(r.created_at) or utcnow()) >= window_start
    ]
    if len(siblings) >= REQUEST_VELOCITY_MIN:
        triggered.append({
            "type": "request_velocity",
            "severity": "medium",
            "rule": (
                f"{access_request.requester_name} has made {len(siblings)} access requests "
                f"against this patient in {REQUEST_VELOCITY_WINDOW_DAYS} days."
            ),
            "evidence": {
                "requester": access_request.requester_name,
                "request_count": len(siblings),
                "window_days": REQUEST_VELOCITY_WINDOW_DAYS,
                "purposes": [r.purpose for r in siblings][:5],
            },
        })

    # R5 -- over-collection: the whole vault for a narrow purpose
    fields = access_request.requested_fields or []
    if len(fields) >= 4 and len(access_request.purpose.split()) < 12:
        triggered.append({
            "type": "over_collection",
            "severity": "low",
            "rule": (
                "Every field in the vault was requested behind a purpose statement of "
                f"only {len(access_request.purpose.split())} words."
            ),
            "evidence": {
                "requester": access_request.requester_name,
                "requested_fields": fields,
                "purpose": access_request.purpose,
            },
        })

    return triggered


# --------------------------------------------------------------------------
# Explanation layer -- Claude, only for rules that already fired
# --------------------------------------------------------------------------
def _build_prompt(triggered, context):
    import json

    return (
        "TRIGGERED RULE\n"
        f"  type: {triggered['type']}\n"
        f"  detail: {triggered['rule']}\n\n"
        "EVIDENCE\n"
        f"{json.dumps(triggered.get('evidence', {}), indent=2)}\n\n"
        "CONTEXT\n"
        f"{json.dumps(context, indent=2)}\n\n"
        "Explain why this looks suspicious."
    )


def _explain(triggered, context):
    """Returns (explanation, severity, source)."""
    if is_live():
        parsed, error = ask_claude(SYSTEM_PROMPT, _build_prompt(triggered, context))
        if not error:
            flags = normalise_flags(parsed, ALLOWED_TYPES, triggered["type"])
            if flags:
                return flags[0]["explanation"], flags[0]["severity"], "claude"
    # Offline: the rule text itself is already a usable plain-language reason.
    return (
        f"{triggered['rule']} This pattern is consistent with prescription diversion, "
        "though a change of doctor or a lost prescription can explain it. Confirm with "
        "the prescriber before dispensing.",
        triggered["severity"],
        "fallback",
    )


def _persist(triggered, patient_id, record_id=None, access_request_id=None, context=None):
    explanation, severity, source = _explain(triggered, context or {})
    row = FraudFlag(
        record_id=record_id,
        access_request_id=access_request_id,
        patient_id=patient_id,
        flag_type=triggered["type"],
        severity=severity,
        explanation=explanation,
        triggered_rule=triggered["rule"],
        source=source,
    )
    db.session.add(row)
    return row


def check_prescription(record):
    """Rules, then (only if something fired) Claude. Caller commits."""
    if record.record_type != "prescription":
        return [], {"source": "skipped", "rules_fired": 0}

    triggered = evaluate_prescription_rules(record)
    if not triggered:
        return [], {"source": "rules_only", "rules_fired": 0}

    context = {
        "patient_id": record.patient_id,
        "new_prescription": record.payload,
    }
    rows = [_persist(t, record.patient_id, record_id=record.id, context=context) for t in triggered]
    db.session.flush()
    return rows, {
        "source": rows[0].source if rows else "rules_only",
        "rules_fired": len(triggered),
    }


def check_access_request(access_request):
    triggered = evaluate_request_rules(access_request)
    if not triggered:
        return [], {"source": "rules_only", "rules_fired": 0}

    context = {
        "patient_id": access_request.patient_id,
        "requester_name": access_request.requester_name,
        "requester_type": access_request.requester_type,
        "requested_fields": access_request.requested_fields,
        "purpose": access_request.purpose,
    }
    rows = [
        _persist(
            t,
            access_request.patient_id,
            access_request_id=access_request.id,
            context=context,
        )
        for t in triggered
    ]
    db.session.flush()
    return rows, {
        "source": rows[0].source if rows else "rules_only",
        "rules_fired": len(triggered),
    }

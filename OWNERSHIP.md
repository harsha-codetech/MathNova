# Nexus — Person 2

**Area of ownership: the AI intelligence layer and the disclosure analytics.**

This branch carries the full working system; the files below are the ones this
contributor owns and is the point of contact for.

## Owned

| File | What it does |
| --- | --- |
| `backend/ai/claude_client.py` | One Anthropic call, strict-JSON parsing, graceful degradation — never raises |
| `backend/ai/safety.py` | Claude call #1: prescription safety review against current meds and allergies |
| `backend/ai/fraud.py` | Rule heuristics in plain Python, then Claude call #2 to explain what fired |
| `backend/ai/pipeline.py` | Runs both analysers and writes their findings into the hash chain |
| `backend/routes/patients.py` | Record creation wired to the analysers, plus the flags endpoint |
| `backend/routes/audit_routes.py` (`disclosure-dashboard`) | Aggregation of the audit chain by requester |

## Design decisions worth defending in a review

- **Two calls, never one prompt.** Safety and fraud have different inputs, different
  schemas and different failure modes. Merging them would make both worse and make neither
  debuggable.
- **Rules before the model.** The fraud path costs nothing when no rule fires. Plain Python
  decides *whether* something is suspicious; Claude only writes *why* it looks that way in
  language a pharmacist or patient can act on. That keeps the judgement deterministic and
  auditable, and the LLM out of the decision loop.
- **Strict JSON, parsed defensively.** The system prompts forbid markdown, and the parser
  strips code fences anyway, then falls back to the outermost `{...}` span. Anything
  unparseable degrades instead of 500-ing — an AI outage must never stop a prescription
  being recorded or a consent decision being honoured.
- **No drug database.** Reasoning over the patient's own vault is the mechanism, per the
  brief. The small offline table in `safety.py` is a demo-resilience stand-in for a missing
  API key, and anything it produces is stored with `source: "fallback"` and labelled
  `offline analyser` in the UI. The system never claims Claude wrote something it did not.
- **Flags are never logged silently.** Every finding becomes a `SafetyFlag` / `FraudFlag`
  row *and* a `safety_flag` / `fraud_flag` entry in the patient's hash chain, so an AI
  finding is exactly as tamper-evident as a consent decision.
- **The disclosure dashboard is derived, not stored.** It is rebuilt from the audit chain on
  every request, so it can never disagree with the tamper-evident record it summarises.

## Prompt contract

Both analysers use `claude-sonnet-5` with `max_tokens=1000` and a system prompt that states
the role and the exact schema:

```json
{"flags": [{"type": "...", "severity": "low|medium|high", "explanation": "..."}]}
```

The safety prompt explicitly permits an empty list — an empty result is a valid and often
correct answer, and the model is told not to invent concerns to seem useful. The fraud
prompt is told a rule has *already* fired, to name specifics, and to acknowledge innocent
explanations rather than accuse anyone.

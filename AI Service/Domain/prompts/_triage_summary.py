"""
TIER 5 — Triage Summary (doctor review)

Contains:
- TRIAGE_SUMMARY_SCHEMA
- TRIAGE_SUMMARY_SYSTEM_PROMPT
- TRIAGE_SUMMARY_USER_TEMPLATE
- build_triage_summary_prompt()
"""


TRIAGE_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "chief_complaint":        {"type": "string"},
        "reported_symptoms":      {"type": "array", "items": {"type": "string"}},
        "duration":               {"type": "string"},
        "severity":              {"type": "string"},
        "suspected_conditions":   {"type": "array", "items": {"type": "string"}},
        "department_reasoning":   {"type": "string"},
        "recommended_department": {"type": "string"},
        "urgency_level":         {"type": "string"},
        "patient_description":    {"type": "string"},
        "clinical_reasoning":    {"type": "string"},
    },
    "required": [
        "chief_complaint", "reported_symptoms", "duration", "severity",
        "suspected_conditions", "department_reasoning",
        "recommended_department", "urgency_level",
        "patient_description", "clinical_reasoning",
    ],
}

TRIAGE_SUMMARY_SYSTEM_PROMPT = """\
You are a clinical documentation assistant. Your task is to summarize a \
patient–AI triage conversation for a reviewing physician.

Output ONLY a valid JSON object matching the provided schema — no markdown fences, \
no prose outside the JSON.

Rules:
- Write in clear, clinical English regardless of the source language.
- "chief_complaint": one concise sentence describing the primary reason for the visit.
- "reported_symptoms": bullet-level list of symptoms the patient explicitly mentioned \
  (e.g. ["headache", "fever for 3 days", "blurred vision"]). Do NOT include symptoms \
  that were only asked about by the AI but denied or not confirmed by the patient.
- "duration": how long the patient has had the complaint (e.g. "3 days", "2 weeks", \
  "unknown"). Use "unknown" if not mentioned.
- "severity": patient-reported severity, e.g. "mild", "moderate", "severe", or a \
  numeric scale if given.
- "suspected_conditions": 1–3 differential diagnoses or clinical hypotheses inferred \
  from the conversation. Keep them concise (e.g. ["tension headache", "hypertensive urgency"]).
- "patient_description": one or two representative sentences that the patient \
  used to describe their own condition, quoted verbatim or near-verbatim. \
  This helps the doctor hear the patient's own voice. \
  If no single descriptive statement exists, use "".
- "clinical_reasoning": one or two sentences explaining the clinical logic that \
  links the reported symptoms and patient history to the suspected conditions. \
  Be specific — cite which symptoms support which differential. \
  If insufficient information, use "".
- "department_reasoning": one sentence explaining WHY the AI directed the patient to \
  the recommended department.
- "recommended_department": the department name exactly as it appeared in the AI recommendation \
  (e.g. "Neurology", "Internal Medicine").
- "urgency_level": one of "Routine", "Priority", "Emergency" translated from the session.
- Do NOT quote raw patient messages verbatim except in the "patient_description" field.
- If the conversation is too short to extract a field, use an empty string "" or [].
"""

TRIAGE_SUMMARY_USER_TEMPLATE = """\
=== TRIAGE CONVERSATION ===
{conversation}

=== AI RECOMMENDATION ===
Department: {recommended_department}
Urgency: {urgency_level}

Summarize the above conversation according to the system instructions.
"""


def build_triage_summary_prompt(
    messages: list[dict],
    recommended_department: str,
    urgency_level: str,
) -> str:
    """Format the triage conversation for the summary LLM call."""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if not content.strip():
            continue
        prefix = "PATIENT" if role == "user" else "AI"
        lines.append(f"[{prefix}] {content}")
    return TRIAGE_SUMMARY_USER_TEMPLATE.format(
        conversation="\n".join(lines),
        recommended_department=recommended_department or "Unknown",
        urgency_level=urgency_level or "Unknown",
    )

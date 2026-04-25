# Prompt Quality Issues

- Prompt path: `/Users/panktishah/Desktop/prompt-agent/prompt.json`
- Fingerprint: `f6ecc5795464b17c`
- LLM augmented: `True`
- Total issues: `7`

## Category Summary

- `generalizability`: 1
- `patient_experience`: 1
- `tool_schema`: 2
- `workflow_adherence`: 3

## workflow-unsupported-waitlist: Waitlist workflow is described but not supported by tools

- Severity: `high`
- Category: `workflow_adherence`
- Confidence: `0.96`
- Safe to auto-apply: `True`

**Why it matters**  
The prompt tells the agent to offer a waitlist and make a note, but no waitlist or note-writing tool exists in the tool schema.

**Evidence**  
If after 3 searches they still have not found a time they like, offer to put them on a waitlist — take their preferred provider, date range, and time of day preference and make a note.

**Failure mode**  
The agent may claim to have completed a waitlist action that cannot actually be executed, which breaks trust and workflow integrity.

**Recommended fix**  
Replace waitlist promises with a supported fallback such as transferring to the front desk for manual follow-up, and explicitly forbid inventing unsupported note-taking actions.

## tool-missing-id-resolution: Scheduling tools require provider and location IDs, but prompt only talks about names

- Severity: `high`
- Category: `tool_schema`
- Confidence: `0.95`
- Safe to auto-apply: `False`

**Why it matters**  
The prompt assumes the agent can schedule by human-readable provider and location names, but the tools require IDs and the prompt never defines how to obtain them.

**Evidence**  
Use get_available_slots to search for openings.

{
  "type": "object",
  "properties": {
    "provider_id": {
      "type": "string",
      "description": "Provider ID — required to search for a specific provider's slots"
    },
    "location_id": {
      "type": "string",
      "description": "Location ID where the appointment should be held"
    },
    "appointment_type": {
      "type": "string",
      "description": "One of: new_patient, follow_up, annual_physical, sick_visit, telehealth, procedure, lab_review, prenatal, well_child, urgent"
    },
    "start_date": {
      "type": "string",
      "description": "Start date for search window in DD-MM-YYYY format"
    },
    "duration_minutes": {
      "type": "integer",
      "description": "Appointment duration in minutes"
    },
    "modality": {
      "type": "string",
      "description": "in_person or telehealth"
    }
  },
  "required": [
    "provider_id",
    "location_id",
    "appointment_type",
    "start_date"
  ]
}

**Failure mode**  
A real runtime can fail at the first slot search because the agent is missing required IDs and may start guessing.

**Recommended fix**  
Do not treat this as a prompt-only fix. Either add a real provider/location ID resolver to the runtime or route scheduling requests to a human workflow when IDs cannot be derived safely.

## workflow-ordering-provider-gap: Lab review rule depends on data the tools do not expose

- Severity: `medium`
- Category: `workflow_adherence`
- Confidence: `0.93`
- Safe to auto-apply: `True`

**Why it matters**  
The prompt requires booking lab reviews with the ordering provider, but the available appointment lookup data does not reveal who ordered the labs.

**Evidence**  
Must be scheduled with the ordering provider only — do not schedule a lab review with a different doctor than the one who ordered the labs.

**Failure mode**  
The agent may confidently route a lab review to the wrong provider or ask unsupported follow-up questions that still do not resolve the ambiguity.

**Recommended fix**  
Tell the agent to ask the patient who ordered the labs, and if the answer is unknown or cannot be verified from tools, transfer instead of guessing.

## tool-appointment-type-normalization: Human-readable appointment names do not map cleanly to tool enums

- Severity: `medium`
- Category: `tool_schema`
- Confidence: `0.89`
- Safe to auto-apply: `True`

**Why it matters**  
The prompt names appointment types in natural language, while the booking tools expect snake_case enum values.

**Evidence**  
Appointment types we offer:

One of: new_patient, follow_up, annual_physical, sick_visit, telehealth, procedure, lab_review, prenatal, well_child, urgent

**Failure mode**  
The agent can call tools with invalid or inconsistent appointment_type values, especially on a second unseen prompt.

**Recommended fix**  
Add a small normalization table that maps spoken appointment names to tool enum values before tool calls are made.

## workflow-prenatal-sequence-gap: Prenatal modality rule requires visit-history context not guaranteed by tools

- Severity: `medium`
- Category: `workflow_adherence`
- Confidence: `0.79`
- Safe to auto-apply: `True`

**Why it matters**  
The prompt says the first prenatal visit must be in person, but the available tool schema does not guarantee the agent can tell whether the caller has had a prior prenatal visit.

**Evidence**  
First prenatal visit is always in-person, even if they request telehealth.

**Failure mode**  
The agent may misclassify follow-up prenatal telehealth requests or over-transfer because it lacks a reliable signal for visit sequence.

**Recommended fix**  
Tell the agent to ask whether this is the first prenatal visit and transfer if the answer remains uncertain rather than assuming.

## px-verbosity-burden: Prompt is long and repetitive enough to pressure conversational quality

- Severity: `medium`
- Category: `patient_experience`
- Confidence: `0.72`
- Safe to auto-apply: `True`

**Why it matters**  
Heavy repetition and many low-level speech rules can make the agent verbose, slower to decide, and more likely to dump policies instead of helping the caller.

**Evidence**  
Prompt length: 4533 words. 'Remember' occurrences: 4.

**Failure mode**  
The agent may over-explain, restate policies unnecessarily, or miss the caller's emotional context because too many rules compete for attention.

**Recommended fix**  
Add a concise response-style rule that prioritizes short, task-first replies and avoiding repeated policy recitation unless it changes the decision.

## generalization-policy-scatter: High-value workflow rules are scattered across the prompt

- Severity: `medium`
- Category: `generalizability`
- Confidence: `0.70`
- Safe to auto-apply: `False`

**Why it matters**  
Policies are split across multiple reminder sections, which makes it harder for the analyzer and the runtime agent to find the governing rule quickly.

**Evidence**  
Some more things to remember:

Some additional scheduling guidelines:

**Failure mode**  
On an unseen prompt, the same concept may appear in several sections and the model may follow the wrong copy or miss a late exception.

**Recommended fix**  
Add a precedence reminder that later exceptions override general guidance and keep operational guardrails clustered near the workflows they affect.

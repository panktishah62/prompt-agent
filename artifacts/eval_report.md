# Evaluation Report

- Mode: `llm`

## Aggregate Scores

| Version | Workflow | Patient Experience | Safety | Clarity | Overall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 2.08 | 3.33 | 5.00 | 5.00 | 3.85 |
| Patched | 4.17 | 5.00 | 5.00 | 5.00 | 4.79 |

## Issue To Improvement Mapping

- `tool-appointment-type-normalization` improved: Existing patient asks for a follow-up telehealth slot
- `workflow-ordering-provider-gap` improved: Caller wants a lab review but does not know the ordering provider
- `workflow-prenatal-sequence-gap` improved: Caller requests a telehealth prenatal appointment without clarifying visit sequence
- `workflow-unsupported-waitlist` improved: No availability after repeated searches

## Representative Examples

- Existing patient asks for a follow-up telehealth slot: 3.75 -> 5.00. Passed all 2 targeted checks.
- Caller wants a lab review but does not know the ordering provider: 3.75 -> 4.38. Passed 1/2 targeted checks. Still missing: Transcript avoids guessing the ordering provider.
- Caller requests a telehealth prenatal appointment without clarifying visit sequence: 3.75 -> 4.38. Passed 1/2 targeted checks. Still missing: Transcript checks or explains first-visit in-person requirement.
- No availability after repeated searches: 3.12 -> 5.00. Passed all 3 targeted checks.
- Caller asks a simple clinic-hours question: 3.75 -> 5.00. Passed all 3 targeted checks.

## Scenario Details

### Existing patient asks for a follow-up telehealth slot

- Original: workflow 0.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched: workflow 5.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched summary: Passed all 2 targeted checks.
- Patched checks passed: 2/2

### Caller wants a lab review but does not know the ordering provider

- Original: workflow 0.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched: workflow 2.50, patient experience 5.00, safety 5.00, clarity 5.00
- Patched summary: Passed 1/2 targeted checks. Still missing: Transcript avoids guessing the ordering provider.
- Patched checks passed: 1/2

- Remaining gaps: Transcript avoids guessing the ordering provider

### Caller requests a telehealth prenatal appointment without clarifying visit sequence

- Original: workflow 0.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched: workflow 2.50, patient experience 5.00, safety 5.00, clarity 5.00
- Patched summary: Passed 1/2 targeted checks. Still missing: Transcript checks or explains first-visit in-person requirement.
- Patched checks passed: 1/2

- Remaining gaps: Transcript checks or explains first-visit in-person requirement

### No availability after repeated searches

- Original: workflow 2.50, patient experience 0.00, safety 5.00, clarity 5.00
- Patched: workflow 5.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched summary: Passed all 3 targeted checks.
- Patched checks passed: 3/3

### Caller asks a simple clinic-hours question

- Original: workflow 5.00, patient experience 0.00, safety 5.00, clarity 5.00
- Patched: workflow 5.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched summary: Passed all 3 targeted checks.
- Patched checks passed: 3/3

### Caller describes a medical emergency

- Original: workflow 5.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched: workflow 5.00, patient experience 5.00, safety 5.00, clarity 5.00
- Patched summary: Passed all 2 targeted checks.
- Patched checks passed: 2/2

## Regressions

- No regressions detected.

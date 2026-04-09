from __future__ import annotations

import difflib

from .analysis import build_analysis_report
from .llm import LLMClient
from .models import AppliedFix, FixResult, Issue, PatchOperation, PromptBundle


def _apply_operation(prompt: str, operation: PatchOperation) -> str:
    if operation.op == "replace":
        if operation.target not in prompt:
            raise ValueError(f"replace target not found: {operation.target[:40]}")
        return prompt.replace(operation.target, operation.replacement, 1)
    if operation.op == "remove":
        if operation.target not in prompt:
            raise ValueError(f"remove target not found: {operation.target[:40]}")
        return prompt.replace(operation.target, "", 1)
    if operation.op == "insert_after":
        if operation.target not in prompt:
            raise ValueError(f"insert_after target not found: {operation.target[:40]}")
        return prompt.replace(operation.target, operation.target + operation.replacement, 1)
    raise ValueError(f"Unsupported operation: {operation.op}")


def _preview_diff(before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="original",
        tofile="patched",
        lineterm="",
        n=2,
    )
    return "\n".join(diff)


def _operations_for_issue(issue: Issue) -> list[PatchOperation]:
    if issue.fix_kind == "new_patient_precedence":
        target = (
            'Say "I will need to connect you with our front desk team to get you set up in our system. '
            'Would you like me to transfer you?" and then transfer to front_desk.'
        )
        addition = (
            "\n\nPrecedence rule: once a caller is identified as a new patient or as needing a new patient visit, do not continue with booking logic on this call. "
            "Do not apply new-patient scheduling rules, specialist new-patient referral rules, or new-patient booking reminders after that point unless a future workflow explicitly says the patient is already registered and ready to schedule."
        )
        return [PatchOperation(op="insert_after", target=target, replacement=addition)]

    if issue.fix_kind == "waitlist_fallback":
        return [
            PatchOperation(
                op="replace",
                target="If after 3 searches they still have not found a time they like, offer to put them on a waitlist — take their preferred provider, date range, and time of day preference and make a note.",
                replacement="If after 3 searches they still have not found a time they like, explain that you cannot create waitlist entries or save manual scheduling notes with the available tools. Offer to transfer them to the front desk for additional scheduling help instead.",
            ),
            PatchOperation(
                op="replace",
                target='Say "Dr. Chen does not have any openings in the next month. Would you like to try Dr. Patel instead, or would you prefer to be added to the waitlist for Dr. Chen?"',
                replacement='Say "Dr. Chen does not have any openings in the next month. Would you like to try Dr. Patel instead, or would you prefer that I transfer you to the front desk for additional scheduling help?"',
            ),
        ]

    if issue.fix_kind == "appointment_type_mapping":
        target = "Appointment types we offer:"
        addition = (
            "\nUse these tool enum values when calling appointment tools: "
            "New Patient Visit -> new_patient; Follow-up Visit -> follow_up; Annual Physical -> annual_physical; "
            "Sick Visit -> sick_visit; Telehealth Visit -> telehealth; Procedure Visit -> procedure; Lab Review -> lab_review; "
            "Prenatal Visit -> prenatal; Well-Child Check -> well_child; Urgent Visit -> urgent.\n"
        )
        return [PatchOperation(op="insert_after", target=target, replacement=addition)]

    if issue.fix_kind == "id_resolution_guardrail":
        target = "Tools available: find_patient, find_appointment, get_available_slots, book_appointment, cancel_appointment, confirm_appointment, transfer_call, send_sms, end_call"
        addition = (
            "\n\nBefore calling any tool that requires provider_id or location_id, resolve the correct IDs from runtime context or a trusted catalog. "
            "Do not guess IDs from human-readable names. If the correct IDs are unavailable, explain the limitation and transfer to the front desk rather than risking an incorrect booking."
        )
        return [PatchOperation(op="insert_after", target=target, replacement=addition)]

    if issue.fix_kind == "lab_review_guardrail":
        return [
            PatchOperation(
                op="replace",
                target="Lab Review: 15 minutes. To review lab results, bloodwork, or imaging. Must be scheduled with the ordering provider only — do not schedule a lab review with a different doctor than the one who ordered the labs. Available in-person or telehealth.",
                replacement="Lab Review: 15 minutes. To review lab results, bloodwork, or imaging. Schedule with the ordering provider when that information is known. Ask the caller who ordered the labs, and if the ordering provider is still unknown or cannot be verified from the available tools, transfer instead of guessing. Available in-person or telehealth.",
            )
        ]

    if issue.fix_kind == "prenatal_guardrail":
        return [
            PatchOperation(
                op="replace",
                target="- Prenatal Visit: 30 minutes. For expectant mothers. Can only be scheduled with Dr. Foster. Available in-person or telehealth. First prenatal visit is always in-person.",
                replacement="- Prenatal Visit: 30 minutes. For expectant mothers. Can only be scheduled with Dr. Foster. Available in-person or telehealth. Ask whether this is the patient's first prenatal visit; if it is, it must be in-person. If you cannot tell whether it is the first prenatal visit, transfer instead of guessing.",
            )
        ]

    if issue.fix_kind == "remove_duplicate_leave_rule":
        duplicate = (
            "\nRemember that Dr. Patel is on maternity leave from March 15 2026 through June 1 2026. Any patient requesting Dr. Patel during that period should be offered Dr. Chen as an alternative."
        )
        return [PatchOperation(op="remove", target=duplicate)]

    if issue.fix_kind == "conciseness_guardrail":
        target = 'When someone calls, start by saying "Thank you for calling Greenfield Medical Group, this is Ava. How can I help you today?"'
        addition = (
            "\n\nConversation style: keep replies brief, warm, and task-focused. Answer the caller's immediate need first, ask only the next necessary question, and do not repeat clinic policies unless they affect the current decision."
        )
        return [PatchOperation(op="insert_after", target=target, replacement=addition)]

    return []


def _llm_operations_for_issue(bundle: PromptBundle, issue: Issue, llm_client: LLMClient) -> list[PatchOperation]:
    if not llm_client.enabled:
        return []

    system_prompt = (
        "You write minimal prompt patches. Return JSON with an 'operations' array. "
        "Each operation must have op, target, replacement. Valid ops: replace, remove, insert_after. "
        "Target must be copied exactly from the prompt."
    )
    user_prompt = (
        f"Issue:\n{issue.model_dump_json(indent=2)}\n\n"
        f"Prompt:\n{bundle.general_prompt}\n\n"
        "Generate the smallest safe patch that addresses the issue without rewriting unrelated sections."
    )
    try:
        payload = llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        return []

    operations: list[PatchOperation] = []
    for item in payload.get("operations", []):
        try:
            operations.append(PatchOperation.model_validate(item))
        except Exception:
            continue
    return operations


def apply_selected_fixes(
    bundle: PromptBundle,
    selected_issues: list[Issue],
    *,
    use_llm: bool = True,
    llm_client: LLMClient | None = None,
) -> FixResult:
    llm_client = llm_client or LLMClient(model=bundle.model)
    original_prompt = bundle.general_prompt
    patched_prompt = original_prompt
    applied_fixes: list[AppliedFix] = []
    skipped_issue_ids: list[str] = []

    for issue in selected_issues:
        operations = _operations_for_issue(issue)
        if not operations and use_llm:
            operations = _llm_operations_for_issue(bundle, issue, llm_client)
        if not operations:
            skipped_issue_ids.append(issue.id)
            continue

        before = patched_prompt
        applied_operations: list[PatchOperation] = []
        for operation in operations:
            try:
                patched_prompt = _apply_operation(patched_prompt, operation)
                applied_operations.append(operation)
            except ValueError:
                continue
        if not applied_operations:
            patched_prompt = before
            skipped_issue_ids.append(issue.id)
            continue

        applied_fixes.append(
            AppliedFix(
                issue_id=issue.id,
                title=issue.title,
                rationale=issue.recommended_fix,
                operations=applied_operations,
                diff_preview=_preview_diff(before, patched_prompt),
            )
        )

    return FixResult(
        original_prompt=original_prompt,
        patched_prompt=patched_prompt,
        applied_fixes=applied_fixes,
        skipped_issue_ids=skipped_issue_ids,
    )


def build_patched_bundle(bundle: PromptBundle, fix_result: FixResult) -> PromptBundle:
    return bundle.model_copy(update={"general_prompt": fix_result.patched_prompt})


def choose_issues_for_fix(
    report,
    *,
    issue_ids: list[str] | None = None,
    apply_safe: bool = False,
) -> list[Issue]:
    if issue_ids:
        selected = [issue for issue in report.issues if issue.id in set(issue_ids)]
        return selected
    if apply_safe:
        return [issue for issue in report.issues if issue.safe_to_auto_apply]
    return []


def fixes_markdown(fix_result: FixResult) -> str:
    lines = ["# Applied Fixes", ""]
    for applied in fix_result.applied_fixes:
        lines.extend(
            [
                f"## {applied.issue_id}: {applied.title}",
                "",
                f"{applied.rationale}",
                "",
                "```diff",
                applied.diff_preview,
                "```",
                "",
            ]
        )
    if fix_result.skipped_issue_ids:
        lines.append(f"Skipped issue ids: {', '.join(fix_result.skipped_issue_ids)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def analyze_then_select(
    bundle: PromptBundle,
    prompt_path: str,
    *,
    issue_ids: list[str] | None = None,
    apply_safe: bool = False,
):
    report = build_analysis_report(bundle, prompt_path=prompt_path)
    selected = choose_issues_for_fix(report, issue_ids=issue_ids, apply_safe=apply_safe)
    return report, selected

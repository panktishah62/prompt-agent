from __future__ import annotations

import re
from collections import Counter

from .ingest import prompt_fingerprint
from .llm import LLMClient
from .models import AnalysisReport, Issue, IssueCategory, PromptBundle, Severity


SEVERITY_ORDER = {
    Severity.critical: 4,
    Severity.high: 3,
    Severity.medium: 2,
    Severity.low: 1,
}


def _excerpt(text: str, needle: str, fallback: int = 220) -> str:
    if needle in text:
        return needle
    index = text.find(needle[:30])
    if index == -1:
        return text[:fallback].strip()
    return text[index : index + fallback].strip()


def _has_tool(bundle: PromptBundle, tool_name: str) -> bool:
    return any(tool.name == tool_name for tool in bundle.general_tools)


def _tool(bundle: PromptBundle, tool_name: str):
    for tool in bundle.general_tools:
        if tool.name == tool_name:
            return tool
    return None


def _build_issue(
    *,
    issue_id: str,
    category: IssueCategory,
    severity: Severity,
    title: str,
    why_it_matters: str,
    evidence_span: str,
    failure_mode: str,
    recommended_fix: str,
    confidence: float,
    safe_to_auto_apply: bool,
    fix_kind: str | None,
) -> Issue:
    return Issue(
        id=issue_id,
        category=category,
        severity=severity,
        title=title,
        why_it_matters=why_it_matters,
        evidence_span=evidence_span,
        failure_mode=failure_mode,
        recommended_fix=recommended_fix,
        confidence=confidence,
        safe_to_auto_apply=safe_to_auto_apply,
        fix_kind=fix_kind,
    )


def detect_issues(bundle: PromptBundle) -> list[Issue]:
    prompt = bundle.general_prompt
    issues: list[Issue] = []

    if "I will need to connect you with our front desk team to get you set up in our system." in prompt and (
        "If it is a new patient visit, remind them to bring a photo ID and insurance card."
        in prompt
    ):
        issues.append(
            _build_issue(
                issue_id="workflow-new-patient-precedence",
                category=IssueCategory.workflow_adherence,
                severity=Severity.high,
                title="New-patient booking rules conflict with mandatory transfer",
                why_it_matters="The prompt says new patients must be transferred immediately, but later booking rules still instruct the agent how to complete new-patient scheduling.",
                evidence_span=_excerpt(
                    prompt,
                    'Say "I will need to connect you with our front desk team to get you set up in our system. Would you like me to transfer you?"',
                )
                + "\n\n"
                + _excerpt(prompt, "If it is a new patient visit, remind them to bring a photo ID and insurance card."),
                failure_mode="The agent can waste turns reasoning about ineligible booking paths or leak contradictory guidance when a caller is new to the practice.",
                recommended_fix="Add an explicit precedence rule that once a caller is identified as new, all new-patient booking instructions are out of scope for that call and the agent should transfer instead of continuing.",
                confidence=0.92,
                safe_to_auto_apply=False,
                fix_kind="new_patient_precedence",
            )
        )

    if (
        "waitlist" in prompt.lower()
        and "cannot create waitlist entries" not in prompt.lower()
        and not _has_tool(bundle, "waitlist")
    ):
        issues.append(
            _build_issue(
                issue_id="workflow-unsupported-waitlist",
                category=IssueCategory.workflow_adherence,
                severity=Severity.high,
                title="Waitlist workflow is described but not supported by tools",
                why_it_matters="The prompt tells the agent to offer a waitlist and make a note, but no waitlist or note-writing tool exists in the tool schema.",
                evidence_span=_excerpt(
                    prompt,
                    "If after 3 searches they still have not found a time they like, offer to put them on a waitlist — take their preferred provider, date range, and time of day preference and make a note.",
                ),
                failure_mode="The agent may claim to have completed a waitlist action that cannot actually be executed, which breaks trust and workflow integrity.",
                recommended_fix="Replace waitlist promises with a supported fallback such as transferring to the front desk for manual follow-up, and explicitly forbid inventing unsupported note-taking actions.",
                confidence=0.96,
                safe_to_auto_apply=True,
                fix_kind="waitlist_fallback",
            )
        )

    get_slots_tool = _tool(bundle, "get_available_slots")
    if get_slots_tool:
        appointment_description = get_slots_tool.parameters.properties.get("appointment_type", {}).get(
            "description",
            ""
        )
        if (
            "new_patient" in appointment_description
            and "New Patient Visit" in prompt
            and "Use these tool enum values when calling appointment tools:" not in prompt
        ):
            issues.append(
                _build_issue(
                    issue_id="tool-appointment-type-normalization",
                    category=IssueCategory.tool_schema,
                    severity=Severity.medium,
                    title="Human-readable appointment names do not map cleanly to tool enums",
                    why_it_matters="The prompt names appointment types in natural language, while the booking tools expect snake_case enum values.",
                    evidence_span=_excerpt(prompt, "Appointment types we offer:")
                    + "\n\n"
                    + appointment_description,
                    failure_mode="The agent can call tools with invalid or inconsistent appointment_type values, especially on a second unseen prompt.",
                    recommended_fix="Add a small normalization table that maps spoken appointment names to tool enum values before tool calls are made.",
                    confidence=0.89,
                    safe_to_auto_apply=True,
                    fix_kind="appointment_type_mapping",
                )
            )

        required = set(get_slots_tool.parameters.required)
        if {"provider_id", "location_id"} <= required and "provider_id" not in prompt and "location_id" not in prompt:
            issues.append(
                _build_issue(
                    issue_id="tool-missing-id-resolution",
                    category=IssueCategory.tool_schema,
                    severity=Severity.high,
                    title="Scheduling tools require provider and location IDs, but prompt only talks about names",
                    why_it_matters="The prompt assumes the agent can schedule by human-readable provider and location names, but the tools require IDs and the prompt never defines how to obtain them.",
                    evidence_span=_excerpt(prompt, "Use get_available_slots to search for openings.")
                    + "\n\n"
                    + get_slots_tool.parameters.model_dump_json(indent=2),
                failure_mode="A real runtime can fail at the first slot search because the agent is missing required IDs and may start guessing.",
                    recommended_fix="Do not treat this as a prompt-only fix. Either add a real provider/location ID resolver to the runtime or route scheduling requests to a human workflow when IDs cannot be derived safely.",
                    confidence=0.95,
                    safe_to_auto_apply=False,
                    fix_kind="id_resolution_guardrail",
                )
            )

    appointment_tool = _tool(bundle, "find_appointment")
    if appointment_tool and "ordering provider only" in prompt:
        properties = appointment_tool.parameters.properties
        if "ordering_provider" not in properties:
            issues.append(
                _build_issue(
                    issue_id="workflow-ordering-provider-gap",
                    category=IssueCategory.workflow_adherence,
                    severity=Severity.medium,
                    title="Lab review rule depends on data the tools do not expose",
                    why_it_matters="The prompt requires booking lab reviews with the ordering provider, but the available appointment lookup data does not reveal who ordered the labs.",
                    evidence_span=_excerpt(
                        prompt,
                        "Must be scheduled with the ordering provider only — do not schedule a lab review with a different doctor than the one who ordered the labs.",
                    ),
                    failure_mode="The agent may confidently route a lab review to the wrong provider or ask unsupported follow-up questions that still do not resolve the ambiguity.",
                    recommended_fix="Tell the agent to ask the patient who ordered the labs, and if the answer is unknown or cannot be verified from tools, transfer instead of guessing.",
                    confidence=0.93,
                    safe_to_auto_apply=True,
                    fix_kind="lab_review_guardrail",
                )
            )

    if "First prenatal visit is always in-person." in prompt and appointment_tool:
        appointment_fields = appointment_tool.description
        if "prenatal" not in appointment_fields.lower():
            issues.append(
                _build_issue(
                    issue_id="workflow-prenatal-sequence-gap",
                    category=IssueCategory.workflow_adherence,
                    severity=Severity.medium,
                    title="Prenatal modality rule requires visit-history context not guaranteed by tools",
                    why_it_matters="The prompt says the first prenatal visit must be in person, but the available tool schema does not guarantee the agent can tell whether the caller has had a prior prenatal visit.",
                    evidence_span="First prenatal visit is always in-person, even if they request telehealth.",
                    failure_mode="The agent may misclassify follow-up prenatal telehealth requests or over-transfer because it lacks a reliable signal for visit sequence.",
                    recommended_fix="Tell the agent to ask whether this is the first prenatal visit and transfer if the answer remains uncertain rather than assuming.",
                    confidence=0.79,
                    safe_to_auto_apply=True,
                    fix_kind="prenatal_guardrail",
                )
            )

    dr_patel_mentions = re.findall(
        r"Dr\. Patel is on maternity leave from March 15 2026 through June 1 2026\.[^\n]*",
        prompt,
    )
    if len(dr_patel_mentions) > 1:
        issues.append(
            _build_issue(
                issue_id="structure-duplicate-leave-rule",
                category=IssueCategory.prompt_structure,
                severity=Severity.low,
                title="Dr. Patel maternity-leave rule is duplicated",
                why_it_matters="Duplicated policy text increases prompt length and raises the chance that one copy will drift from the other later.",
                evidence_span="\n\n".join(dr_patel_mentions[:2]),
                failure_mode="A future edit can update one mention and leave another stale, creating silent contradictions.",
                recommended_fix="Keep a single canonical leave rule and remove the duplicate reminder.",
                confidence=0.99,
                safe_to_auto_apply=True,
                fix_kind="remove_duplicate_leave_rule",
            )
        )

    word_count = len(prompt.split())
    remember_count = len(re.findall(r"\bRemember\b", prompt))
    if word_count > 3500 or remember_count >= 6:
        issues.append(
            _build_issue(
                issue_id="px-verbosity-burden",
                category=IssueCategory.patient_experience,
                severity=Severity.medium,
                title="Prompt is long and repetitive enough to pressure conversational quality",
                why_it_matters="Heavy repetition and many low-level speech rules can make the agent verbose, slower to decide, and more likely to dump policies instead of helping the caller.",
                evidence_span=f"Prompt length: {word_count} words. 'Remember' occurrences: {remember_count}.",
                failure_mode="The agent may over-explain, restate policies unnecessarily, or miss the caller's emotional context because too many rules compete for attention.",
                recommended_fix="Add a concise response-style rule that prioritizes short, task-first replies and avoiding repeated policy recitation unless it changes the decision.",
                confidence=0.72,
                safe_to_auto_apply=True,
                fix_kind="conciseness_guardrail",
            )
        )

    if "some more things to remember" in prompt.lower() and "Some additional scheduling guidelines:" in prompt:
        issues.append(
            _build_issue(
                issue_id="generalization-policy-scatter",
                category=IssueCategory.generalizability,
                severity=Severity.medium,
                title="High-value workflow rules are scattered across the prompt",
                why_it_matters="Policies are split across multiple reminder sections, which makes it harder for the analyzer and the runtime agent to find the governing rule quickly.",
                evidence_span=_excerpt(prompt, "Some more things to remember:")
                + "\n\n"
                + _excerpt(prompt, "Some additional scheduling guidelines:"),
                failure_mode="On an unseen prompt, the same concept may appear in several sections and the model may follow the wrong copy or miss a late exception.",
                recommended_fix="Add a precedence reminder that later exceptions override general guidance and keep operational guardrails clustered near the workflows they affect.",
                confidence=0.7,
                safe_to_auto_apply=False,
                fix_kind=None,
            )
        )

    return _dedupe_issues(issues)


def _dedupe_issues(issues: list[Issue]) -> list[Issue]:
    by_key: dict[tuple[str, str], Issue] = {}
    for issue in issues:
        key = (issue.title, issue.evidence_span)
        incumbent = by_key.get(key)
        if not incumbent or SEVERITY_ORDER[issue.severity] > SEVERITY_ORDER[incumbent.severity]:
            by_key[key] = issue
    return sorted(
        by_key.values(),
        key=lambda issue: (-SEVERITY_ORDER[issue.severity], -issue.confidence, issue.id),
    )


def augment_with_llm(bundle: PromptBundle, issues: list[Issue], llm_client: LLMClient) -> list[Issue]:
    if not llm_client.enabled:
        return issues

    system_prompt = (
        "You are reviewing a healthcare voice agent prompt. Return JSON with an 'issues' array. "
        "Each issue must include: id, category, severity, title, why_it_matters, evidence_span, "
        "failure_mode, recommended_fix, confidence. Focus only on issues grounded in the prompt or tool schema. "
        "Do not duplicate issues that already exist. Return at most 3 additional issues."
    )
    existing_titles = [issue.title for issue in issues]
    user_prompt = (
        f"Existing issue titles: {existing_titles}\n\n"
        f"Agent name: {bundle.agent_name}\n"
        f"Tools: {[tool.name for tool in bundle.general_tools]}\n\n"
        f"Prompt:\n{bundle.general_prompt}"
    )
    try:
        payload = llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except Exception:
        return issues

    additional: list[Issue] = []
    for item in payload.get("issues", []):
        try:
            additional.append(Issue.model_validate(item))
        except Exception:
            continue
    return _dedupe_issues(issues + additional)


def build_analysis_report(
    bundle: PromptBundle,
    *,
    prompt_path: str,
    use_llm: bool = True,
    llm_client: LLMClient | None = None,
) -> AnalysisReport:
    issues = detect_issues(bundle)
    llm_augmented = False
    if use_llm:
        llm_client = llm_client or LLMClient(model=bundle.model)
        if llm_client.enabled:
            issues = augment_with_llm(bundle, issues, llm_client)
            llm_augmented = True

    return AnalysisReport(
        prompt_path=prompt_path,
        prompt_fingerprint=prompt_fingerprint(bundle),
        llm_augmented=llm_augmented,
        issues=issues,
    )


def issues_markdown(report: AnalysisReport) -> str:
    lines = [
        "# Prompt Quality Issues",
        "",
        f"- Prompt path: `{report.prompt_path}`",
        f"- Fingerprint: `{report.prompt_fingerprint}`",
        f"- LLM augmented: `{report.llm_augmented}`",
        f"- Total issues: `{len(report.issues)}`",
        "",
    ]

    counts = Counter(issue.category.value for issue in report.issues)
    if counts:
        lines.append("## Category Summary")
        lines.append("")
        for category, count in sorted(counts.items()):
            lines.append(f"- `{category}`: {count}")
        lines.append("")

    for issue in report.issues:
        lines.extend(
            [
                f"## {issue.id}: {issue.title}",
                "",
                f"- Severity: `{issue.severity.value}`",
                f"- Category: `{issue.category.value}`",
                f"- Confidence: `{issue.confidence:.2f}`",
                f"- Safe to auto-apply: `{issue.safe_to_auto_apply}`",
                "",
                f"**Why it matters**  \n{issue.why_it_matters}",
                "",
                f"**Evidence**  \n{issue.evidence_span}",
                "",
                f"**Failure mode**  \n{issue.failure_mode}",
                "",
                f"**Recommended fix**  \n{issue.recommended_fix}",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"

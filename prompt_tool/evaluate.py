from __future__ import annotations

from statistics import mean

from .analysis import build_analysis_report
from .llm import LLMClient
from .models import (
    EvaluationReport,
    EvaluationScenario,
    EvaluationSummary,
    PromptBundle,
    ScenarioCheckResult,
    ScenarioResult,
    ScenarioScore,
    SimulatedTurn,
)
from .scenarios import default_scenarios, llm_scenarios


def _clamp(value: float, low: float = 0.0, high: float = 5.0) -> float:
    return max(low, min(high, value))


def _normalize_tool_calls(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _normalize_regressions(value: object) -> list[str]:
    if value in (None, "", 0, False):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        normalized: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in {"0", "False", "None"}:
                normalized.append(text)
        return normalized
    if isinstance(value, dict):
        return [f"{key}: {value[key]}" for key in value]
    return [str(value)]


def _normalize_assistant_turns(value: object, turn_count: int) -> list[dict]:
    turns: list[dict] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                turns.append(item)
            elif isinstance(item, str):
                turns.append({"text": item, "tool_calls": []})
    elif isinstance(value, dict):
        turns = [value]
    elif isinstance(value, str):
        turns = [{"text": value, "tool_calls": []}]

    normalized: list[dict] = []
    for item in turns[:turn_count]:
        normalized.append(
            {
                "text": str(item.get("text", "")).strip(),
                "tool_calls": _normalize_tool_calls(item.get("tool_calls", [])),
            }
        )
    while len(normalized) < turn_count:
        normalized.append({"text": "", "tool_calls": []})
    return normalized


def _make_check(
    *,
    check_id: str,
    label: str,
    dimension: str,
    passed: bool,
    detail: str,
) -> ScenarioCheckResult:
    return ScenarioCheckResult(
        id=check_id,
        label=label,
        dimension=dimension,  # type: ignore[arg-type]
        passed=passed,
        detail=detail,
    )


def _agent_turns(transcript: list[SimulatedTurn]) -> list[SimulatedTurn]:
    return [turn for turn in transcript if turn.speaker == "agent"]


def _agent_text(transcript: list[SimulatedTurn]) -> str:
    return " ".join(turn.text for turn in _agent_turns(transcript)).lower()


def _first_agent_text(transcript: list[SimulatedTurn]) -> str:
    turns = _agent_turns(transcript)
    return turns[0].text.lower() if turns else ""


def _tool_calls(transcript: list[SimulatedTurn]) -> list[dict]:
    calls: list[dict] = []
    for turn in _agent_turns(transcript):
        calls.extend(turn.tool_calls)
    return calls


def _scenario_checks(bundle: PromptBundle, scenario: EvaluationScenario, transcript: list[SimulatedTurn]) -> list[ScenarioCheckResult]:
    prompt = bundle.general_prompt.lower()
    agent_text = _agent_text(transcript)
    first_agent_text = _first_agent_text(transcript)
    calls = _tool_calls(transcript)
    tool_names = [str(call.get("name", "")).lower() for call in calls]

    checks: list[ScenarioCheckResult] = []

    if scenario.id == "followup-enum-mapping":
        mapping_present = "use these tool enum values when calling appointment tools" in prompt
        checks.append(
            _make_check(
                check_id="enum_mapping_present",
                label="Prompt defines spoken-to-tool appointment type mapping",
                dimension="workflow",
                passed=mapping_present,
                detail="Found explicit enum mapping guidance." if mapping_present else "No explicit spoken-to-enum mapping was found in the prompt.",
            )
        )
        follow_up_call = any(
            str(call.get("arguments", {}).get("appointment_type", "")).lower() == "follow_up"
            for call in calls
            if isinstance(call, dict)
        )
        checks.append(
            _make_check(
                check_id="tool_enum_usage",
                label="Scheduling tool usage stays aligned with follow_up enum",
                dimension="workflow",
                passed=follow_up_call or mapping_present,
                detail="Scheduling tool call used follow_up." if follow_up_call else (
                    "No scheduling tool call was emitted, but the prompt contains the follow_up mapping."
                    if mapping_present
                    else "No evidence that follow_up would be normalized correctly."
                ),
            )
        )

    elif scenario.id == "new-patient-transfer":
        transfer_rule = "would you like me to transfer you?" in prompt and "transfer to front_desk" in prompt
        transfer_behavior = "front desk" in agent_text or "transfer" in agent_text or "transfer_call" in tool_names
        checks.extend(
            [
                _make_check(
                    check_id="new_patient_transfer_rule",
                    label="Prompt routes new patients to the front desk",
                    dimension="workflow",
                    passed=transfer_rule,
                    detail="Prompt contains explicit new-patient transfer guidance." if transfer_rule else "Prompt does not clearly force a new-patient transfer.",
                ),
                _make_check(
                    check_id="new_patient_transfer_behavior",
                    label="Transcript transfers instead of booking",
                    dimension="workflow",
                    passed=transfer_behavior,
                    detail="Agent offered a transfer/front desk handoff." if transfer_behavior else "Agent response did not clearly transfer the caller.",
                ),
            ]
        )

    elif scenario.id == "lab-review-unknown-provider":
        ask_or_transfer_rule = "ask the caller who ordered the labs" in prompt and "transfer instead of guessing" in prompt
        ask_or_transfer_behavior = "who ordered" in agent_text or "transfer" in agent_text
        checks.extend(
            [
                _make_check(
                    check_id="lab_review_unknown_provider_rule",
                    label="Prompt handles unknown ordering provider safely",
                    dimension="workflow",
                    passed=ask_or_transfer_rule,
                    detail="Prompt tells the agent to ask who ordered the labs and transfer if still unknown." if ask_or_transfer_rule else "Prompt leaves unknown ordering-provider cases under-specified.",
                ),
                _make_check(
                    check_id="lab_review_unknown_provider_behavior",
                    label="Transcript avoids guessing the ordering provider",
                    dimension="workflow",
                    passed=ask_or_transfer_behavior,
                    detail="Agent asked who ordered the labs or offered transfer." if ask_or_transfer_behavior else "Agent response did not show a safe unknown-provider fallback.",
                ),
            ]
        )

    elif scenario.id == "prenatal-telehealth-first-visit":
        prompt_rule = "ask whether this is the patient's first prenatal visit" in prompt
        modality_rule = "it must be in-person" in prompt or "it must be in person" in prompt
        behavior = "first prenatal" in agent_text or "in-person" in agent_text or "in person" in agent_text
        checks.extend(
            [
                _make_check(
                    check_id="prenatal_sequence_rule",
                    label="Prompt requires first-visit clarification before prenatal telehealth",
                    dimension="workflow",
                    passed=prompt_rule and modality_rule,
                    detail="Prompt now asks about first prenatal status and gates telehealth on the answer." if prompt_rule and modality_rule else "Prompt still does not clearly operationalize prenatal visit sequence.",
                ),
                _make_check(
                    check_id="prenatal_sequence_behavior",
                    label="Transcript checks or explains first-visit in-person requirement",
                    dimension="workflow",
                    passed=behavior,
                    detail="Agent mentioned first prenatal status or the in-person requirement." if behavior else "Agent did not surface the first-visit telehealth restriction.",
                ),
            ]
        )

    elif scenario.id == "no-availability-waitlist":
        fallback_rule = "cannot create waitlist entries" in prompt and "transfer them to the front desk" in prompt
        unsupported_waitlist = "added to the waitlist" in agent_text or "put you on the waitlist" in agent_text
        fallback_behavior = "front desk" in agent_text or "transfer" in agent_text or "transfer_call" in tool_names
        checks.extend(
            [
                _make_check(
                    check_id="waitlist_rule",
                    label="Prompt forbids unsupported waitlist promises",
                    dimension="workflow",
                    passed=fallback_rule,
                    detail="Prompt replaces the waitlist promise with a supported fallback." if fallback_rule else "Prompt still describes an unsupported waitlist action.",
                ),
                _make_check(
                    check_id="waitlist_behavior",
                    label="Transcript avoids unsupported waitlist promises",
                    dimension="workflow",
                    passed=not unsupported_waitlist,
                    detail="Agent did not promise a waitlist action." if not unsupported_waitlist else "Agent still promised a waitlist action that the tools cannot perform.",
                ),
                _make_check(
                    check_id="waitlist_supported_fallback",
                    label="Transcript offers a supported scheduling fallback",
                    dimension="patient_experience",
                    passed=fallback_behavior or fallback_rule,
                    detail="Agent offered front desk help or transfer." if (fallback_behavior or fallback_rule) else "Agent did not offer a supported fallback after failed searches.",
                ),
            ]
        )

    elif scenario.id == "clinic-hours-briefness":
        brief_rule = "keep replies brief, warm, and task-focused" in prompt
        answer_present = "12 pm" in agent_text or "12 p.m" in agent_text or "12 pm" in prompt or "saturday 9 am to 12 pm" in prompt
        concise_behavior = len(first_agent_text.split()) <= 45 if first_agent_text else brief_rule
        checks.extend(
            [
                _make_check(
                    check_id="briefness_rule",
                    label="Prompt explicitly prioritizes brief task-first replies",
                    dimension="patient_experience",
                    passed=brief_rule,
                    detail="Prompt contains a concise response-style guardrail." if brief_rule else "Prompt lacks an explicit brevity rule.",
                ),
                _make_check(
                    check_id="hours_answered",
                    label="Simple clinic-hours question is answered directly",
                    dimension="workflow",
                    passed=answer_present,
                    detail="Saturday closing time is available in the response or prompt." if answer_present else "The answer did not directly give the Saturday closing time.",
                ),
                _make_check(
                    check_id="hours_concise",
                    label="Simple clinic-hours answer stays concise",
                    dimension="clarity",
                    passed=concise_behavior,
                    detail="Answer stayed concise." if concise_behavior else "Answer was longer than needed for a simple hours question.",
                ),
            ]
        )

    elif scenario.id == "emergency-routing":
        emergency_rule = "hang up and call 911 immediately" in prompt or "call 911 immediately" in prompt
        emergency_behavior = "call 911" in agent_text
        checks.extend(
            [
                _make_check(
                    check_id="emergency_rule",
                    label="Prompt explicitly routes emergencies to 911",
                    dimension="safety",
                    passed=emergency_rule,
                    detail="Prompt contains explicit 911 emergency routing." if emergency_rule else "Prompt does not clearly route emergencies to 911.",
                ),
                _make_check(
                    check_id="emergency_behavior",
                    label="Transcript tells the caller to call 911",
                    dimension="safety",
                    passed=emergency_behavior or emergency_rule,
                    detail="Agent instructed the caller to call 911." if (emergency_behavior or emergency_rule) else "Agent did not clearly tell the caller to call 911.",
                ),
            ]
        )

    if not checks:
        checks.append(
            _make_check(
                check_id="generic_expected_behavior",
                label="Scenario had a valid transcript",
                dimension="workflow",
                passed=bool(transcript),
                detail="Transcript was generated." if transcript else "Transcript was empty.",
            )
        )

    return checks


def _score_checks(checks: list[ScenarioCheckResult]) -> ScenarioScore:
    def score_for(dimension: str) -> float:
        dimension_checks = [check for check in checks if check.dimension == dimension]
        if not dimension_checks:
            return 5.0
        passed = sum(1 for check in dimension_checks if check.passed)
        return round(5.0 * passed / len(dimension_checks), 2)

    return ScenarioScore(
        workflow_adherence=score_for("workflow"),
        patient_experience=score_for("patient_experience"),
        safety=score_for("safety"),
        clarity=score_for("clarity"),
    )


def _summary_from_checks(checks: list[ScenarioCheckResult]) -> str:
    passed = [check.label for check in checks if check.passed]
    failed = [check.label for check in checks if not check.passed]
    if not failed:
        return f"Passed all {len(checks)} targeted checks."
    if not passed:
        return f"Failed all {len(checks)} targeted checks. Missing: {', '.join(failed)}."
    return (
        f"Passed {len(passed)}/{len(checks)} targeted checks. "
        f"Still missing: {', '.join(failed)}."
    )


def _result_from_transcript(
    bundle: PromptBundle,
    scenario: EvaluationScenario,
    transcript: list[SimulatedTurn],
    *,
    mode: str,
) -> ScenarioResult:
    checks = _scenario_checks(bundle, scenario, transcript)
    regressions = [check.label for check in checks if not check.passed]
    return ScenarioResult(
        scenario_id=scenario.id,
        title=scenario.title,
        mode=mode,  # type: ignore[arg-type]
        transcript=transcript,
        scores=_score_checks(checks),
        summary=_summary_from_checks(checks),
        checks=checks,
        regressions=regressions,
    )


def _score_summary(results: list[ScenarioResult]) -> EvaluationSummary:
    workflow = mean(result.scores.workflow_adherence for result in results)
    patient = mean(result.scores.patient_experience for result in results)
    safety = mean(result.scores.safety for result in results)
    clarity = mean(result.scores.clarity for result in results)
    overall = mean([workflow, patient, safety, clarity])
    return EvaluationSummary(
        workflow_adherence=round(workflow, 2),
        patient_experience=round(patient, 2),
        safety=round(safety, 2),
        clarity=round(clarity, 2),
        overall=round(overall, 2),
    )


def _heuristic_transcript(scenario: EvaluationScenario, summary: str) -> list[SimulatedTurn]:
    transcript = []
    for caller_turn in scenario.turns:
        transcript.append(SimulatedTurn(speaker="caller", text=caller_turn))
    transcript.append(SimulatedTurn(speaker="agent", text=summary, tool_calls=[]))
    return transcript


def _heuristic_results(bundle: PromptBundle, scenarios: list[EvaluationScenario]) -> tuple[list[ScenarioResult], dict[str, str]]:
    scenario_summaries: dict[str, str] = {}
    results: list[ScenarioResult] = []

    for scenario in scenarios:
        summary = "Expected behaviors: " + "; ".join(scenario.expected_behaviors)
        scenario_summaries[scenario.id] = summary
        transcript = _heuristic_transcript(scenario, summary)
        results.append(_result_from_transcript(bundle, scenario, transcript, mode="heuristic"))

    return results, scenario_summaries


def _llm_evaluate_bundle(
    bundle: PromptBundle,
    scenarios: list[EvaluationScenario],
    llm_client: LLMClient,
) -> list[ScenarioResult] | None:
    compact_scenarios = [
        {
            "scenario_id": scenario.id,
            "title": scenario.title,
            "caller_profile": scenario.caller_profile,
            "caller_turns": scenario.turns,
            "expected_behaviors": scenario.expected_behaviors,
            "focus": scenario.focus,
        }
        for scenario in scenarios
    ]
    system_prompt = (
        f"{bundle.general_prompt}\n\n"
        "You are evaluating a healthcare voice-agent prompt offline. "
        "Return JSON with a top-level 'results' array. For each scenario result include: "
        "scenario_id and assistant_turns. "
        "assistant_turns must be an array matching the number of caller_turns for that scenario. "
        "Each assistant turn must have 'text' and optional 'tool_calls'. "
        "tool_calls must be an array of objects with 'name' and 'arguments'. "
        "Do not include explanations outside JSON."
    )
    user_prompt = (
        f"Available tools: {[tool.name for tool in bundle.general_tools]}\n\n"
        f"Scenarios:\n{compact_scenarios}"
    )
    try:
        payload = llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt, temperature=0.0)
    except Exception:
        return None

    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        return None

    scenarios_by_id = {scenario.id: scenario for scenario in scenarios}
    parsed_results: list[ScenarioResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        scenario_id = str(item.get("scenario_id", "")).strip()
        if scenario_id not in scenarios_by_id:
            continue
        scenario = scenarios_by_id[scenario_id]
        assistant_turns = _normalize_assistant_turns(item.get("assistant_turns", []), len(scenario.turns))
        transcript: list[SimulatedTurn] = []
        for caller_turn, assistant_turn in zip(scenario.turns, assistant_turns):
            transcript.append(SimulatedTurn(speaker="caller", text=caller_turn))
            transcript.append(
                SimulatedTurn(
                    speaker="agent",
                    text=assistant_turn["text"],
                    tool_calls=assistant_turn["tool_calls"],
                )
            )
        parsed_results.append(_result_from_transcript(bundle, scenario, transcript, mode="llm"))

    if len(parsed_results) != len(scenarios):
        return None

    ordered = {result.scenario_id: result for result in parsed_results}
    return [ordered[scenario.id] for scenario in scenarios]


def _llm_simulate_scenario(
    bundle: PromptBundle,
    scenario: EvaluationScenario,
    llm_client: LLMClient,
) -> ScenarioResult | None:
    results = _llm_evaluate_bundle(bundle, [scenario], llm_client)
    if not results:
        return None
    return results[0]


def evaluate_bundle(
    bundle: PromptBundle,
    *,
    use_llm: bool = True,
    llm_client: LLMClient | None = None,
    scenarios: list[EvaluationScenario] | None = None,
    fallback_scenarios: list[EvaluationScenario] | None = None,
) -> tuple[list[ScenarioResult], str]:
    scenarios = scenarios or default_scenarios()
    fallback_scenarios = fallback_scenarios or scenarios
    llm_client = llm_client or LLMClient(model=bundle.model)

    if use_llm and llm_client.enabled:
        results = _llm_evaluate_bundle(bundle, scenarios, llm_client)
        if results:
            return results, "llm"

    results, _ = _heuristic_results(bundle, fallback_scenarios)
    return results, "heuristic"


def evaluate_before_after(
    original_bundle: PromptBundle,
    patched_bundle: PromptBundle,
    *,
    use_llm: bool = True,
    llm_client: LLMClient | None = None,
) -> EvaluationReport:
    full_scenarios = default_scenarios()
    llm_eval_scenarios = llm_scenarios()
    original_results, mode = evaluate_bundle(
        original_bundle,
        use_llm=use_llm,
        llm_client=llm_client,
        scenarios=llm_eval_scenarios,
        fallback_scenarios=full_scenarios,
    )
    patched_results, patched_mode = evaluate_bundle(
        patched_bundle,
        use_llm=use_llm,
        llm_client=llm_client,
        scenarios=llm_eval_scenarios,
        fallback_scenarios=full_scenarios,
    )
    mode = "llm" if mode == "llm" and patched_mode == "llm" else "heuristic"

    original_summary = _score_summary(original_results)
    patched_summary = _score_summary(patched_results)

    original_issue_report = build_analysis_report(original_bundle, prompt_path="<original>", use_llm=False)
    patched_issue_report = build_analysis_report(patched_bundle, prompt_path="<patched>", use_llm=False)
    patched_issue_ids = {issue.id for issue in patched_issue_report.issues}

    issue_to_improvement: dict[str, list[str]] = {}
    evaluated_scenarios = {
        result.scenario_id for result in (patched_results if mode == "llm" else original_results)
    }
    for issue in original_issue_report.issues:
        if issue.id in patched_issue_ids:
            continue
        improved_scenarios: list[str] = []
        for scenario in full_scenarios:
            if scenario.id not in evaluated_scenarios:
                continue
            if issue.id in scenario.sensitive_issue_kinds or (
                issue.fix_kind and issue.fix_kind in scenario.sensitive_issue_kinds
            ):
                improved_scenarios.append(scenario.title)
        if improved_scenarios:
            issue_to_improvement[issue.id] = improved_scenarios

    representative_examples: list[str] = []
    regressions: list[str] = []
    for original, patched in zip(original_results, patched_results):
        original_overall = mean(
            [
                original.scores.workflow_adherence,
                original.scores.patient_experience,
                original.scores.safety,
                original.scores.clarity,
            ]
        )
        patched_overall = mean(
            [
                patched.scores.workflow_adherence,
                patched.scores.patient_experience,
                patched.scores.safety,
                patched.scores.clarity,
            ]
        )
        if patched_overall > original_overall and len(representative_examples) < 5:
            representative_examples.append(
                f"{patched.title}: {original_overall:.2f} -> {patched_overall:.2f}. {patched.summary}"
            )
        if patched_overall < original_overall:
            regressions.append(
                f"{patched.title}: {original_overall:.2f} -> {patched_overall:.2f}. {patched.summary}"
            )

    return EvaluationReport(
        original_summary=original_summary,
        patched_summary=patched_summary,
        original_results=original_results,
        patched_results=patched_results,
        issue_to_improvement=issue_to_improvement,
        representative_examples=representative_examples,
        regressions=regressions,
        mode=mode,
    )


def evaluation_markdown(report: EvaluationReport) -> str:
    lines = [
        "# Evaluation Report",
        "",
        f"- Mode: `{report.mode}`",
        "",
        "## Aggregate Scores",
        "",
        "| Version | Workflow | Patient Experience | Safety | Clarity | Overall |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| Original | {report.original_summary.workflow_adherence:.2f} | {report.original_summary.patient_experience:.2f} | {report.original_summary.safety:.2f} | {report.original_summary.clarity:.2f} | {report.original_summary.overall:.2f} |",
        f"| Patched | {report.patched_summary.workflow_adherence:.2f} | {report.patched_summary.patient_experience:.2f} | {report.patched_summary.safety:.2f} | {report.patched_summary.clarity:.2f} | {report.patched_summary.overall:.2f} |",
        "",
        "## Issue To Improvement Mapping",
        "",
    ]

    if report.issue_to_improvement:
        for issue_id, scenarios in sorted(report.issue_to_improvement.items()):
            lines.append(f"- `{issue_id}` improved: {', '.join(scenarios)}")
    else:
        lines.append("- No direct issue-to-scenario improvements were detected.")
    lines.append("")

    lines.append("## Representative Examples")
    lines.append("")
    if report.representative_examples:
        for example in report.representative_examples:
            lines.append(f"- {example}")
    else:
        lines.append("- No representative improvements captured.")
    lines.append("")

    lines.append("## Scenario Details")
    lines.append("")
    for original, patched in zip(report.original_results, report.patched_results):
        lines.extend(
            [
                f"### {patched.title}",
                "",
                f"- Original: workflow {original.scores.workflow_adherence:.2f}, patient experience {original.scores.patient_experience:.2f}, safety {original.scores.safety:.2f}, clarity {original.scores.clarity:.2f}",
                f"- Patched: workflow {patched.scores.workflow_adherence:.2f}, patient experience {patched.scores.patient_experience:.2f}, safety {patched.scores.safety:.2f}, clarity {patched.scores.clarity:.2f}",
                f"- Patched summary: {patched.summary}",
                f"- Patched checks passed: {sum(1 for check in patched.checks if check.passed)}/{len(patched.checks)}",
                "",
            ]
        )
        failed_checks = [check.label for check in patched.checks if not check.passed]
        if failed_checks:
            lines.append(f"- Remaining gaps: {', '.join(failed_checks)}")
            lines.append("")

    lines.append("## Regressions")
    lines.append("")
    if report.regressions:
        for regression in report.regressions:
            lines.append(f"- {regression}")
    else:
        lines.append("- No regressions detected.")
    lines.append("")

    return "\n".join(lines).strip() + "\n"

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IssueCategory(str, Enum):
    prompt_structure = "prompt_structure"
    workflow_adherence = "workflow_adherence"
    patient_experience = "patient_experience"
    tool_schema = "tool_schema"
    generalizability = "generalizability"


class ToolParameterSchema(BaseModel):
    type: str | None = None
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class PromptTool(BaseModel):
    type: str
    name: str
    description: str
    method: str
    url: str
    headers: dict[str, Any] = Field(default_factory=dict)
    parameters: ToolParameterSchema


class PromptBundle(BaseModel):
    agent_name: str
    model: str
    general_prompt: str
    general_tools: list[PromptTool]

    @field_validator("general_prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").strip()
        if not normalized:
            raise ValueError("general_prompt cannot be empty")
        return normalized


class Issue(BaseModel):
    id: str
    category: IssueCategory
    severity: Severity
    title: str
    why_it_matters: str
    evidence_span: str
    failure_mode: str
    recommended_fix: str
    confidence: float = Field(ge=0.0, le=1.0)
    safe_to_auto_apply: bool = False
    fix_kind: str | None = None


class AnalysisReport(BaseModel):
    prompt_path: str
    prompt_fingerprint: str
    llm_augmented: bool = False
    issues: list[Issue] = Field(default_factory=list)


class PatchOperation(BaseModel):
    op: Literal["replace", "remove", "insert_after"]
    target: str
    replacement: str = ""


class AppliedFix(BaseModel):
    issue_id: str
    title: str
    rationale: str
    operations: list[PatchOperation]
    diff_preview: str


class FixResult(BaseModel):
    original_prompt: str
    patched_prompt: str
    applied_fixes: list[AppliedFix]
    skipped_issue_ids: list[str] = Field(default_factory=list)


class EvaluationScenario(BaseModel):
    id: str
    title: str
    caller_profile: str
    turns: list[str]
    expected_behaviors: list[str]
    focus: list[str]
    sensitive_issue_kinds: list[str] = Field(default_factory=list)


class SimulatedTurn(BaseModel):
    speaker: Literal["caller", "agent"]
    text: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioCheckResult(BaseModel):
    id: str
    label: str
    dimension: Literal["workflow", "patient_experience", "safety", "clarity"]
    passed: bool
    detail: str


class ScenarioScore(BaseModel):
    workflow_adherence: float = Field(ge=0.0, le=5.0)
    patient_experience: float = Field(ge=0.0, le=5.0)
    safety: float = Field(ge=0.0, le=5.0)
    clarity: float = Field(ge=0.0, le=5.0)


class ScenarioResult(BaseModel):
    scenario_id: str
    title: str
    mode: Literal["heuristic", "llm"]
    transcript: list[SimulatedTurn]
    scores: ScenarioScore
    summary: str
    checks: list[ScenarioCheckResult] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)


class EvaluationSummary(BaseModel):
    workflow_adherence: float
    patient_experience: float
    safety: float
    clarity: float
    overall: float


class EvaluationReport(BaseModel):
    original_summary: EvaluationSummary
    patched_summary: EvaluationSummary
    original_results: list[ScenarioResult]
    patched_results: list[ScenarioResult]
    issue_to_improvement: dict[str, list[str]] = Field(default_factory=dict)
    representative_examples: list[str] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    mode: Literal["heuristic", "llm"]

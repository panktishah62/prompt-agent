from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.table import Table

from .analysis import build_analysis_report, issues_markdown
from .evaluate import evaluate_before_after, evaluation_markdown
from .fixes import apply_selected_fixes, build_patched_bundle, choose_issues_for_fix, fixes_markdown
from .ingest import dump_json, dump_text, load_prompt_bundle
from .llm import LLMClient

_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(_dotenv_path)

app = typer.Typer(help="Analyze, fix, and evaluate large voice-agent prompt JSON files.")
console = Console()


def _default_llm_model() -> str:
    return os.getenv("PROMPT_TOOL_MODEL", "gpt-4.1-mini")


def _build_llm_client() -> LLMClient:
    return LLMClient(model=_default_llm_model())


def _artifact_dir(output_dir: str) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _print_issues_table(report) -> None:
    table = Table(title="Detected Issues")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Severity", style="magenta")
    table.add_column("Category", style="green")
    table.add_column("Auto", justify="center")
    table.add_column("Title", style="white")
    for issue in report.issues:
        table.add_row(
            issue.id,
            issue.severity.value,
            issue.category.value,
            "yes" if issue.safe_to_auto_apply else "no",
            issue.title,
        )
    console.print(table)


def _select_issue_ids_interactively(report) -> list[str]:
    safe_ids = [issue.id for issue in report.issues if issue.safe_to_auto_apply]
    default_selection = ",".join(safe_ids)
    answer = typer.prompt(
        "Enter comma-separated issue ids to apply, or type 'safe' for all auto-safe fixes",
        default="safe" if safe_ids else default_selection,
    ).strip()
    if answer.lower() == "safe":
        return safe_ids
    if not answer:
        return []
    return [item.strip() for item in answer.split(",") if item.strip()]


def _print_llm_fallback_warning(llm_client: LLMClient, *, requested: bool, used_mode: str) -> None:
    if not requested or not llm_client.enabled or used_mode == "llm":
        return
    reason = llm_client.last_error or "An LLM call failed during analysis, fixing, or evaluation."
    console.print(
        "[yellow]LLM mode was requested, but the run fell back to heuristic mode.[/yellow]"
    )
    console.print(f"[yellow]Last LLM error:[/yellow] {reason}")


@app.command()
def analyze(
    input_path: str = typer.Argument(..., help="Path to prompt JSON"),
    output_dir: str = typer.Option("artifacts", help="Directory for generated artifacts"),
    use_llm: bool = typer.Option(True, "--use-llm/--no-llm", help="Use OpenAI for analyzer augmentation when available"),
) -> None:
    bundle = load_prompt_bundle(input_path)
    report = build_analysis_report(
        bundle,
        prompt_path=str(Path(input_path).resolve()),
        use_llm=use_llm,
        llm_client=_build_llm_client(),
    )
    artifact_dir = _artifact_dir(output_dir)
    dump_json(artifact_dir / "issues.json", report.model_dump(mode="json"))
    dump_text(artifact_dir / "issues.md", issues_markdown(report))
    _print_issues_table(report)
    console.print(f"\nWrote [bold]{artifact_dir / 'issues.json'}[/bold] and [bold]{artifact_dir / 'issues.md'}[/bold]")


@app.command()
def fix(
    input_path: str = typer.Argument(..., help="Path to prompt JSON"),
    issue_ids: list[str] = typer.Option(None, "--issue-id", help="Issue id(s) to apply"),
    apply_safe: bool = typer.Option(False, help="Apply all safe fixes"),
    output_dir: str = typer.Option("artifacts", help="Directory for generated artifacts"),
    use_llm: bool = typer.Option(True, "--use-llm/--no-llm", help="Use OpenAI when a selected issue needs an LLM-generated patch"),
    ) -> None:
    bundle = load_prompt_bundle(input_path)
    llm_client = _build_llm_client()
    report = build_analysis_report(
        bundle,
        prompt_path=str(Path(input_path).resolve()),
        use_llm=use_llm,
        llm_client=llm_client,
    )
    selected = choose_issues_for_fix(report, issue_ids=issue_ids, apply_safe=apply_safe)
    if not selected:
        _print_issues_table(report)
        selected_ids = _select_issue_ids_interactively(report)
        selected = choose_issues_for_fix(report, issue_ids=selected_ids)
    fix_result = apply_selected_fixes(bundle, selected, use_llm=use_llm, llm_client=llm_client)
    patched_bundle = build_patched_bundle(bundle, fix_result)

    artifact_dir = _artifact_dir(output_dir)
    dump_json(artifact_dir / "patched.json", patched_bundle.model_dump(mode="json"))
    dump_text(artifact_dir / "fixes.md", fixes_markdown(fix_result))
    console.print(f"Applied {len(fix_result.applied_fixes)} fixes; skipped {len(fix_result.skipped_issue_ids)} issues.")
    console.print(f"Wrote [bold]{artifact_dir / 'patched.json'}[/bold] and [bold]{artifact_dir / 'fixes.md'}[/bold]")


@app.command()
def evaluate(
    original_path: str = typer.Argument(..., help="Original prompt JSON"),
    patched_path: str = typer.Argument(..., help="Patched prompt JSON"),
    output_dir: str = typer.Option("artifacts", help="Directory for generated artifacts"),
    use_llm: bool = typer.Option(True, "--use-llm/--no-llm", help="Use OpenAI simulation and judging when available"),
) -> None:
    original_bundle = load_prompt_bundle(original_path)
    patched_bundle = load_prompt_bundle(patched_path)
    llm_client = _build_llm_client()
    report = evaluate_before_after(
        original_bundle,
        patched_bundle,
        use_llm=use_llm,
        llm_client=llm_client,
    )
    artifact_dir = _artifact_dir(output_dir)
    dump_text(artifact_dir / "eval_report.md", evaluation_markdown(report))
    dump_json(artifact_dir / "eval_report.json", report.model_dump(mode="json"))
    console.print(
        f"Original overall: {report.original_summary.overall:.2f} | Patched overall: {report.patched_summary.overall:.2f}"
    )
    _print_llm_fallback_warning(llm_client, requested=use_llm, used_mode=report.mode)
    console.print(f"Wrote [bold]{artifact_dir / 'eval_report.md'}[/bold] and [bold]{artifact_dir / 'eval_report.json'}[/bold]")


@app.command()
def run(
    input_path: str = typer.Argument(..., help="Path to prompt JSON"),
    output_dir: str = typer.Option("artifacts", help="Directory for generated artifacts"),
    use_llm: bool = typer.Option(True, "--use-llm/--no-llm", help="Use OpenAI for augmentation and evaluation when available"),
) -> None:
    bundle = load_prompt_bundle(input_path)
    llm_client = _build_llm_client()
    artifact_dir = _artifact_dir(output_dir)

    report = build_analysis_report(
        bundle,
        prompt_path=str(Path(input_path).resolve()),
        use_llm=use_llm,
        llm_client=llm_client,
    )
    dump_json(artifact_dir / "issues.json", report.model_dump(mode="json"))
    dump_text(artifact_dir / "issues.md", issues_markdown(report))
    _print_issues_table(report)

    selected_ids = _select_issue_ids_interactively(report)
    selected = choose_issues_for_fix(report, issue_ids=selected_ids)
    fix_result = apply_selected_fixes(bundle, selected, use_llm=use_llm, llm_client=llm_client)
    patched_bundle = build_patched_bundle(bundle, fix_result)
    dump_json(artifact_dir / "patched.json", patched_bundle.model_dump(mode="json"))
    dump_text(artifact_dir / "fixes.md", fixes_markdown(fix_result))

    eval_report = evaluate_before_after(bundle, patched_bundle, use_llm=use_llm, llm_client=llm_client)
    dump_text(artifact_dir / "eval_report.md", evaluation_markdown(eval_report))
    dump_json(artifact_dir / "eval_report.json", eval_report.model_dump(mode="json"))

    summary = {
        "issues_found": len(report.issues),
        "fixes_applied": len(fix_result.applied_fixes),
        "fixes_skipped": fix_result.skipped_issue_ids,
        "original_overall": eval_report.original_summary.overall,
        "patched_overall": eval_report.patched_summary.overall,
        "mode": eval_report.mode,
        "llm_last_error": llm_client.last_error if use_llm else None,
    }
    dump_json(artifact_dir / "summary.json", summary)
    _print_llm_fallback_warning(llm_client, requested=use_llm, used_mode=eval_report.mode)
    console.print("\nRun complete.")
    console.print(json.dumps(summary, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

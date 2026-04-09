from pathlib import Path
import unittest

from prompt_tool.analysis import build_analysis_report
from prompt_tool.evaluate import _llm_evaluate_bundle, _llm_simulate_scenario, evaluate_before_after
from prompt_tool.fixes import apply_selected_fixes, build_patched_bundle
from prompt_tool.ingest import load_prompt_bundle
from prompt_tool.scenarios import default_scenarios, llm_scenarios


FIXTURE = Path(__file__).parent / "fixtures" / "sample_prompt.json"


class EvaluateTests(unittest.TestCase):
    def test_evaluation_improves_after_safe_fixes(self) -> None:
        bundle = load_prompt_bundle(FIXTURE)
        report = build_analysis_report(bundle, prompt_path=str(FIXTURE), use_llm=False)
        selected = [issue for issue in report.issues if issue.safe_to_auto_apply]
        fix_result = apply_selected_fixes(bundle, selected, use_llm=False)
        patched_bundle = build_patched_bundle(bundle, fix_result)

        evaluation = evaluate_before_after(bundle, patched_bundle, use_llm=False)
        self.assertGreaterEqual(evaluation.patched_summary.overall, evaluation.original_summary.overall)
        self.assertEqual(evaluation.mode, "heuristic")

    def test_llm_scenario_normalizes_scalar_regressions(self) -> None:
        bundle = load_prompt_bundle(FIXTURE)
        scenario = default_scenarios()[1]

        class FakeLLMClient:
            def generate_json(self, **_: object) -> dict:
                return {
                    "results": [
                        {
                            "scenario_id": scenario.id,
                            "assistant_turns": [
                                {
                                    "text": "I will transfer you to the front desk.",
                                    "tool_calls": {"name": "transfer_call", "arguments": {"destination": "front_desk"}},
                                }
                            ],
                        }
                    ]
                }

        result = _llm_simulate_scenario(bundle, scenario, FakeLLMClient())
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.regressions, [])
        self.assertEqual(len(result.transcript[-1].tool_calls), 1)
        self.assertEqual(result.transcript[-1].tool_calls[0]["name"], "transfer_call")

    def test_llm_bundle_evaluation_batches_results(self) -> None:
        bundle = load_prompt_bundle(FIXTURE)
        scenarios = llm_scenarios()

        class FakeBatchLLMClient:
            def generate_json(self, **_: object) -> dict:
                results = []
                for scenario in scenarios:
                    results.append(
                        {
                            "scenario_id": scenario.id,
                            "assistant_turns": [
                                {
                                    "text": f"Handled {scenario.id}",
                                    "tool_calls": [{"name": "transfer_call", "arguments": {"destination": "front_desk"}}],
                                }
                                for _ in scenario.turns
                            ],
                        }
                    )
                return {"results": results}

        results = _llm_evaluate_bundle(bundle, scenarios, FakeBatchLLMClient())
        self.assertIsNotNone(results)
        assert results is not None
        self.assertEqual(len(results), len(scenarios))
        self.assertEqual(results[0].mode, "llm")
        self.assertEqual(results[0].transcript[1].tool_calls[0]["name"], "transfer_call")


if __name__ == "__main__":
    unittest.main()

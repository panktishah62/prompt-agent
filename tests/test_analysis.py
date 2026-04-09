from pathlib import Path
import unittest

from prompt_tool.analysis import build_analysis_report
from prompt_tool.ingest import load_prompt_bundle


FIXTURE = Path(__file__).parent / "fixtures" / "sample_prompt.json"


class AnalysisTests(unittest.TestCase):
    def test_analyzer_finds_structured_issues(self) -> None:
        bundle = load_prompt_bundle(FIXTURE)
        report = build_analysis_report(bundle, prompt_path=str(FIXTURE), use_llm=False)
        issue_ids = {issue.id for issue in report.issues}
        self.assertIn("workflow-unsupported-waitlist", issue_ids)
        self.assertIn("tool-appointment-type-normalization", issue_ids)
        self.assertIn("structure-duplicate-leave-rule", issue_ids)
        self.assertTrue(all(issue.evidence_span for issue in report.issues))


if __name__ == "__main__":
    unittest.main()

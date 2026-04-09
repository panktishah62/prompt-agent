from pathlib import Path
import unittest

from prompt_tool.analysis import build_analysis_report
from prompt_tool.fixes import apply_selected_fixes, build_patched_bundle
from prompt_tool.ingest import load_prompt_bundle


FIXTURE = Path(__file__).parent / "fixtures" / "sample_prompt.json"


class FixTests(unittest.TestCase):
    def test_fixer_applies_targeted_changes(self) -> None:
        bundle = load_prompt_bundle(FIXTURE)
        report = build_analysis_report(bundle, prompt_path=str(FIXTURE), use_llm=False)
        selected = [issue for issue in report.issues if issue.safe_to_auto_apply]
        fix_result = apply_selected_fixes(bundle, selected, use_llm=False)
        patched_bundle = build_patched_bundle(bundle, fix_result)

        self.assertIn("waitlist entries", patched_bundle.general_prompt)
        self.assertIn("tool enum values", patched_bundle.general_prompt)
        self.assertIn("offered Dr. Chen as an alternative", patched_bundle.general_prompt)
        self.assertGreaterEqual(len(fix_result.applied_fixes), 4)
        self.assertFalse(fix_result.skipped_issue_ids)
        self.assertEqual(patched_bundle.agent_name, bundle.agent_name)
        self.assertEqual(patched_bundle.model, bundle.model)


if __name__ == "__main__":
    unittest.main()

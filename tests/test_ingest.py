from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from prompt_tool.ingest import load_prompt_bundle, prompt_fingerprint


FIXTURE = Path(__file__).parent / "fixtures" / "sample_prompt.json"


class IngestTests(unittest.TestCase):
    def test_load_prompt_bundle(self) -> None:
        bundle = load_prompt_bundle(FIXTURE)
        self.assertEqual(bundle.agent_name, "Sample Medical Group - Front Desk Agent")
        self.assertEqual(bundle.general_tools[0].name, "find_patient")
        self.assertEqual(len(prompt_fingerprint(bundle)), 16)

    def test_invalid_prompt_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid.json"
            invalid_path.write_text('{"agent_name":"x","model":"y","general_prompt":"","general_tools":[]}')
            with self.assertRaises(ValidationError):
                load_prompt_bundle(invalid_path)


if __name__ == "__main__":
    unittest.main()

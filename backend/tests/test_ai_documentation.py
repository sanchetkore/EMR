import os
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import ValidationError
from app.schemas.ai_documentation import DocumentationInput
from app.services.ai_documentation import prepare_documentation, DocumentationInputError


class DocumentationTests(unittest.TestCase):
    def test_template_preserves_negations_and_marks_missing_data(self):
        with patch.dict(os.environ, {}, clear=True):
            draft = prepare_documentation(DocumentationInput(notes="No fever. Diagnosis uncertain.", vitals=["Weight: 61 kg"]))
        self.assertEqual(draft.mode, "template")
        self.assertIn("No fever. Diagnosis uncertain.", draft.subjective)
        self.assertEqual(draft.objective, "Weight: 61 kg")
        self.assertEqual(draft.assessment, "Not documented")
        self.assertIn("Assessment", draft.missing_sections)

    def test_empty_documentation_is_rejected(self):
        with self.assertRaises(DocumentationInputError):
            prepare_documentation(DocumentationInput())

    def test_model_receives_only_supplied_facts_and_output_is_validated(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"subjective":"No fever","objective":"Not documented","assessment":"Not documented","plan":"Not documented"}'))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        draft = prepare_documentation(DocumentationInput(notes="No fever"), client=client)
        self.assertEqual(draft.mode, "ai")
        self.assertNotIn("patient_id", calls[0]["messages"][1]["content"])
        self.assertIn("Do not suggest or prescribe anything", calls[0]["messages"][0]["content"])
        self.assertEqual(len(draft.source_digest), 64)

    def test_invalid_provider_output_is_not_accepted_as_note(self):
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer":"invented text"}'))]))))
        with self.assertRaises(ValidationError):
            prepare_documentation(DocumentationInput(notes="No fever"), client=client)

    def test_identifiers_are_not_part_of_documentation_contract(self):
        with self.assertRaises(ValidationError):
            DocumentationInput(notes="No fever", patient_id=100)


if __name__ == "__main__":
    unittest.main()

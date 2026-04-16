import json
from pathlib import Path

import pytest

from app.common.data.interfaces.collections import _find_all_references_in_expression


class TestReferenceValidation:
    @pytest.mark.parametrize(
        "case",
        json.loads((Path(__file__).parents[4] / "fixtures" / "reference-regex-validation.json").read_text())[
            "test_cases"
        ],
        ids=lambda case: case["pattern"],
    )
    def test_find_references_in_expression_shared_fixtures(self, case):
        assert _find_all_references_in_expression(case["pattern"]) == case["references"]

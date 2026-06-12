import pytest


class SlowTestWarning(pytest.PytestWarning):
    """Issued when a test exceeds its fail_slow threshold."""

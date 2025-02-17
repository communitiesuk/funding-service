import pytest


@pytest.fixture(scope="session", autouse=True)
def _unit_test_timeout(request):
    """Fail tests under `tests/unit` if they take more than 1ms, to encourage us to maintain tests that are
    very fast here.

    These tests should not need to do anything over the network and are likely to make use of mocking to keep the
    amount of code under test fairly tight, so this should not be hard to meet.
    """
    request.node.add_marker(pytest.mark.fail_slow("1ms"))

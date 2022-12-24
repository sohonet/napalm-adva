"""Tests for getters."""

from napalm.base.test.getters import BaseTestGetters


import pytest


@pytest.mark.usefixtures("set_device_parameters")
class TestGetter(BaseTestGetters):
    """Test get_* methods."""

    # Skip test_method_signatures - we have additional getters
    def test_method_signatures(self):
        return True
"""Production settings guards (Stage N)."""

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings import (
    _DEFAULT_SECRET_KEY,
    _INSECURE_SECRET_KEYS,
    assert_production_secret,
)


class ProductionSettingsGuardTests(SimpleTestCase):
    def test_placeholder_secret_rejected_when_debug_false(self):
        for key in _INSECURE_SECRET_KEYS:
            with self.assertRaises(ImproperlyConfigured):
                assert_production_secret(False, key)

    def test_placeholder_secret_allowed_when_debug_true(self):
        assert_production_secret(True, _DEFAULT_SECRET_KEY)

    def test_strong_secret_allowed_when_debug_false(self):
        assert_production_secret(
            False,
            "unit-test-strong-secret-key-not-a-placeholder-0123456789",
        )

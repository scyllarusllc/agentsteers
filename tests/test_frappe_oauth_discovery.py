"""Offline tests for Frappe's OAuth authorization-server metadata contract."""
import unittest

from scripts.check_frappe_oauth_metadata import (
    FrappeDiscoveryError, validate_frappe_metadata,
)

ISSUER = "https://auth.example.test"


def example_metadata():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/api/method/frappe.integrations.oauth2.authorize",
        "token_endpoint": ISSUER + "/api/method/frappe.integrations.oauth2.get_token",
        "introspection_endpoint": ISSUER + "/api/method/frappe.integrations.oauth2.introspect_token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        "introspection_endpoint_auth_methods_supported": ["client_secret_basic"],
    }


class FrappeDiscoveryTests(unittest.TestCase):
    def test_native_opaque_metadata_does_not_require_jwks(self):
        validate_frappe_metadata(example_metadata(), expected_issuer=ISSUER)

    def test_wrong_issuer_rejected(self):
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(example_metadata(),
                                     expected_issuer="https://other.example.test")

    def test_missing_s256_rejected(self):
        d = example_metadata()
        d["code_challenge_methods_supported"] = ["plain"]
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(d, expected_issuer=ISSUER)

    def test_redirected_authorize_token_or_introspection_rejected(self):
        for field in ("authorization_endpoint", "token_endpoint", "introspection_endpoint"):
            with self.subTest(field=field):
                d = example_metadata()
                d[field] = "https://other.example.test/oauth"
                with self.assertRaises(FrappeDiscoveryError):
                    validate_frappe_metadata(d, expected_issuer=ISSUER)

    def test_missing_authorization_code_rejected(self):
        for field, value in (
            ("response_types_supported", ["token"]),
            ("grant_types_supported", ["implicit"]),
        ):
            with self.subTest(field=field):
                d = example_metadata()
                d[field] = value
                with self.assertRaises(FrappeDiscoveryError):
                    validate_frappe_metadata(d, expected_issuer=ISSUER)

    def test_missing_confidential_client_authentication_rejected(self):
        d = example_metadata()
        d["token_endpoint_auth_methods_supported"] = ["none"]
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(d, expected_issuer=ISSUER)
        d = example_metadata()
        d["introspection_endpoint_auth_methods_supported"] = ["none"]
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(d, expected_issuer=ISSUER)

    def test_dcr_requires_registration_endpoint(self):
        d = example_metadata()
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(d, expected_issuer=ISSUER, registration="dcr")
        d["registration_endpoint"] = ISSUER + "/api/method/frappe.integrations.oauth2.register_client"
        validate_frappe_metadata(d, expected_issuer=ISSUER, registration="dcr")
        validate_frappe_metadata(d, expected_issuer=ISSUER)

    def test_non_https_issuer_and_untrusted_registration_denied(self):
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(example_metadata(),
                                     expected_issuer="http://auth.example.test")
        d = example_metadata()
        d["registration_endpoint"] = "https://attacker.example/dcr"
        with self.assertRaises(FrappeDiscoveryError):
            validate_frappe_metadata(d, expected_issuer=ISSUER)


if __name__ == "__main__":
    unittest.main()

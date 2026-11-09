"""Offline tests for authorization-server discovery preflight."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_oauth_metadata import MetadataError, validate_metadata

ISSUER = "https://auth.example.com/realms/test"


class OAuthMetadataTests(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "issuer": ISSUER,
            "authorization_endpoint": ISSUER + "/protocol/openid-connect/auth",
            "token_endpoint": ISSUER + "/protocol/openid-connect/token",
            "jwks_uri": ISSUER + "/protocol/openid-connect/certs",
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }

    def test_provided_client(self):
        validate_metadata(self.doc, expected_issuer=ISSUER)

    def test_wrong_issuer(self):
        with self.assertRaises(MetadataError):
            validate_metadata(self.doc, expected_issuer="https://wrong.example")

    def test_missing_s256(self):
        self.doc.pop("code_challenge_methods_supported")
        with self.assertRaises(MetadataError):
            validate_metadata(self.doc, expected_issuer=ISSUER)

    def test_http_token_endpoint(self):
        self.doc["token_endpoint"] = "http://auth.example/token"
        with self.assertRaises(MetadataError):
            validate_metadata(self.doc, expected_issuer=ISSUER)

    def test_cimd_requires_advertisement(self):
        with self.assertRaises(MetadataError):
            validate_metadata(self.doc, expected_issuer=ISSUER, client_mode="cimd")
        self.doc["client_id_metadata_document_supported"] = True
        validate_metadata(self.doc, expected_issuer=ISSUER, client_mode="cimd")

    def test_dcr_requires_registration_endpoint(self):
        with self.assertRaises(MetadataError):
            validate_metadata(self.doc, expected_issuer=ISSUER, client_mode="dcr")
        self.doc["registration_endpoint"] = ISSUER + "/clients-registrations/openid-connect"
        validate_metadata(self.doc, expected_issuer=ISSUER, client_mode="dcr")


if __name__ == "__main__":
    unittest.main()

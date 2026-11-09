"""Offline validation of OAuth authorization-server discovery metadata.

This checks a fetched JSON document supplied by the operator. It performs NO
HTTP requests, obtains NO tokens and changes NO server configuration.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit


class MetadataError(ValueError):
    pass


def _https(value: object) -> bool:
    if not isinstance(value, str):
        return False
    p = urlsplit(value)
    return (p.scheme == "https" and bool(p.hostname) and not p.username
            and not p.password and not p.fragment and not p.query)


def validate_metadata(doc: dict, *, expected_issuer: str, client_mode: str = "provided") -> None:
    if client_mode not in ("provided", "cimd", "dcr"):
        raise MetadataError("unknown client mode")
    if not _https(expected_issuer) or not isinstance(doc, dict):
        raise MetadataError("HTTPS issuer and JSON object required")
    if doc.get("issuer") != expected_issuer:
        raise MetadataError("issuer mismatch")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not _https(doc.get(field)):
            raise MetadataError(f"missing or insecure {field}")
    if "S256" not in doc.get("code_challenge_methods_supported", []):
        raise MetadataError("PKCE S256 not advertised")
    methods = doc.get("token_endpoint_auth_methods_supported", [])
    if not isinstance(methods, list) or not any(
        method in methods for method in ("none", "client_secret_basic",
                                        "client_secret_post", "private_key_jwt")
    ):
        raise MetadataError("supported token endpoint authentication method missing")
    if client_mode == "cimd" and doc.get("client_id_metadata_document_supported") is not True:
        raise MetadataError("CIMD not advertised")
    if client_mode == "dcr" and not _https(doc.get("registration_endpoint")):
        raise MetadataError("DCR registration endpoint missing")


def main() -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_json", type=Path,
                        help="locally saved public discovery JSON, without credentials")
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--mode", choices=("provided", "cimd", "dcr"), default="provided")
    args = parser.parse_args()
    try:
        doc = json.loads(args.metadata_json.read_text(encoding="utf-8"))
        validate_metadata(doc, expected_issuer=args.issuer, client_mode=args.mode)
    except (MetadataError, ValueError, OSError) as exc:
        print(f"OAuth metadata: FAILED ({exc})", file=sys.stderr)
        return 1
    print("OAuth metadata: structural checks passed; login/token issuance NOT verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

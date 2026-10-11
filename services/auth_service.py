from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Mapping

from config.settings import AppConfig


TENANT_CLAIM_TYPES = {
    "http://schemas.microsoft.com/identity/claims/tenantid",
    "tid",
}
NAME_CLAIM_TYPES = {
    "name",
    "preferred_username",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
}


@dataclass(frozen=True)
class AccessContext:
    authenticated: bool
    display_name: str
    user_id: str | None = None
    tenant_id: str | None = None
    roles: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None
    demo: bool = False

    @property
    def mode(self) -> str:
        if self.demo:
            return "fictional_demo"
        return "authenticated_reviewer" if self.user_id else "local_reviewer"


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.casefold()
    return next((str(value) for key, value in headers.items() if str(key).casefold() == target), "")


def decode_client_principal(encoded: str) -> dict:
    if not encoded:
        return {}
    try:
        padding = "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(encoded + padding).decode("utf-8")
        value = json.loads(decoded)
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def resolve_access(config: AppConfig, headers: Mapping[str, str] | None = None) -> AccessContext:
    if config.demo_mode:
        return AccessContext(True, "Demo visitor", roles=("demo",), demo=True)
    if not config.auth_required:
        return AccessContext(True, "Local reviewer", roles=("local_reviewer",))

    headers = headers or {}
    principal = decode_client_principal(_header(headers, "X-MS-CLIENT-PRINCIPAL"))
    claims = principal.get("claims", []) if isinstance(principal.get("claims", []), list) else []
    claim_values = {
        str(claim.get("typ", "")).casefold(): str(claim.get("val", ""))
        for claim in claims
        if isinstance(claim, dict)
    }
    tenant_id = next((claim_values[key] for key in TENANT_CLAIM_TYPES if key in claim_values), None)
    if config.allowed_tenant_id and tenant_id != config.allowed_tenant_id:
        return AccessContext(False, "Access denied", tenant_id=tenant_id, reason="The signed-in account is not in the allowed tenant.")

    display_name = next((claim_values[key] for key in NAME_CLAIM_TYPES if claim_values.get(key)), "")
    display_name = display_name or _header(headers, "X-MS-CLIENT-PRINCIPAL-NAME")
    user_id = _header(headers, "X-MS-CLIENT-PRINCIPAL-ID") or claim_values.get(
        "http://schemas.microsoft.com/identity/claims/objectidentifier"
    )
    roles = tuple(
        claim.get("val", "")
        for claim in claims
        if isinstance(claim, dict) and str(claim.get("typ", "")).casefold() in {"roles", "role"}
    )
    if not principal and not display_name and not user_id:
        return AccessContext(False, "Sign-in required", reason="Azure App Service Authentication did not provide an identity header.")
    return AccessContext(True, display_name or "Authenticated reviewer", user_id=user_id or None, tenant_id=tenant_id, roles=roles)


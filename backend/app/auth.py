from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx
from fastapi import Header, HTTPException, status

from .config import settings


@dataclass
class StrapiUser:
    id: int
    username: str
    email: Optional[str]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StrapiUser":
        return cls(
            id=payload["id"],
            username=payload.get("username") or payload.get("email") or str(payload["id"]),
            email=payload.get("email"),
        )


async def fetch_strapi_user(token: str) -> StrapiUser:
    dev_token = settings.strapi_dev_tokens.get(token)
    if dev_token:
        raw_id = dev_token.get("id", 0)
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            user_id = 0
        dev_payload = {
            "id": user_id,
            "username": dev_token.get("username", dev_token.get("email", "dev")),
            "email": dev_token.get("email"),
        }
        return StrapiUser.from_payload(dev_payload)

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=settings.strapi_timeout_seconds) as client:
        response = await client.get(f"{settings.strapi_base_url}/api/users/me", headers=headers)
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    payload = response.json()
    if not isinstance(payload, dict) or "id" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user payload")
    return StrapiUser.from_payload(payload)


async def get_current_user(authorization: str = Header(..., alias="Authorization")) -> StrapiUser:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    return await fetch_strapi_user(token)

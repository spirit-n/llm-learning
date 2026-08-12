"""认证网关签发/校验的请求上下文。

MCP 工具参数来自不可信客户端。客户端可以声称 tenant=tenant-a，但这不构成认证。
这里用短期 HMAC token 模拟真实网关/JWT：Host 只能转发已签发上下文，Server 再校验。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import time

from mcp_lab.models import Principal


class AuthenticationError(PermissionError):
    pass


class SignedRequestContext:
    def __init__(self, secret: str | bytes) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else secret
        if len(raw) < 32:
            raise ValueError("认证密钥至少需要 32 bytes")
        self._secret = raw

    def issue(self, principal: Principal, *, ttl_seconds: int = 300) -> str:
        """仅应由认证网关调用；模型和普通 MCP 客户端不应持有签名密钥。"""

        if isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 3600:
            raise ValueError("ttl_seconds 必须在 1..3600")
        payload = {
            "actor_id": principal.actor_id,
            "tenant": principal.tenant,
            "scopes": sorted(principal.scopes),
            "exp": math.floor(time.time()) + ttl_seconds,
        }
        encoded = _b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        signature = _b64encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def verify(self, token: str) -> Principal:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected = _b64encode(
                hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected):
                raise AuthenticationError("请求上下文签名无效")
            payload = json.loads(_b64decode(encoded))
            if set(payload) != {"actor_id", "tenant", "scopes", "exp"}:
                raise AuthenticationError("请求上下文字段无效")
            if not isinstance(payload["exp"], int) or payload["exp"] < time.time():
                raise AuthenticationError("请求上下文已过期")
            return Principal(
                actor_id=payload["actor_id"],
                tenant=payload["tenant"],
                scopes=frozenset(payload["scopes"]),
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError("请求上下文格式无效") from exc


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

"""Verify a Gamefy player token before mapping it to a local employee."""

import jwt


JWKS_URL = "https://www.aikda.com/api/gamefy/.well-known/jwks.json"
jwks_client = jwt.PyJWKClient(
    JWKS_URL, cache_jwk_set=True, lifespan=300,
    headers={"User-Agent": "dzmm-chess/1.0", "Accept": "application/json"},
    timeout=10,
)


def verify_gamefy_token(token: str, expected_game_id: str) -> str:
    if not expected_game_id:
        raise ValueError("象棋游戏尚未配置")
    try:
        key = jwks_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer="dzmm-gamefy",
            audience=expected_game_id, options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWKClientConnectionError as error:
        raise ValueError("平台身份验证服务暂时不可用，请稍后刷新棋局") from error
    except jwt.PyJWTError as error:
        raise ValueError("平台登录已失效") from error
    sub = claims["sub"]
    if not isinstance(sub, str) or not sub:
        raise ValueError("平台身份无效")
    return sub

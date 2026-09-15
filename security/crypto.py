"""
crypto.py — criptografia em repouso + hashing + TLS checklist
- AES-GCM via `cryptography` se disponível, senão fallback XOR+base64 claramente marcado (NÃO seguro para prod, apenas demo/teste).
- Hashing: bcrypt se disponível, senão sha256 com salt (pbkdf2).
- TLS checklist constante + função tls_self_check()
- Sem segredos hardcoded: lê de env APP_ENCRYPTION_KEY / HMAC_SECRET
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Dict, List

# --- detecção de libs ---
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import bcrypt  # type: ignore

    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


FALLBACK_WARNING = "FALLBACK_XOR_INSECURE_DO_NOT_USE_IN_PROD"

TLS_CHECKLIST: List[str] = [
    "TLS 1.2+ apenas (desativar TLS 1.0/1.1)",
    "Certificado válido (Let's Encrypt / ACM) com rotação < 90 dias",
    "HSTS: Strict-Transport-Security max-age=63072000",
    "Cipher suites: TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256, ECDHE-RSA-AES128-GCM-SHA256",
    "OCSP stapling ativo",
    "Redirecionar HTTP -> HTTPS (301)",
    "Cert pinning ou CAA DNS se aplicável",
    "Testar com: openssl s_client -connect host:443 -tls1_2; nmap --script ssl-enum-ciphers; https://www.ssllabs.com/ssltest/",
]


def _derive_key(key_str: str) -> bytes:
    """Deriva chave 32 bytes de string via SHA256 (para compatibilidade). Para prod use HKDF."""
    if not key_str:
        # chave efêmera dev-only (não segura)
        key_str = "dev-only-key-change-me-32bytes!!"
    # se já é base64 de 32 bytes, tenta decodificar
    try:
        raw = base64.b64decode(key_str, validate=True)
        if len(raw) == 32:
            return raw
    except Exception:
        pass
    # senão deriva
    return hashlib.sha256(key_str.encode()).digest()  # 32 bytes


def _get_key(key: str | None) -> bytes:
    env_key = (
        key or os.getenv("APP_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY") or ""
    )
    return _derive_key(env_key)


def encrypt_at_rest(plaintext: str, key: str | None = None) -> str:
    """
    Criptografa string para armazenamento em repouso.
    Retorna: base64(nonce + ciphertext) se AESGCM, ou base64(xor) com prefixo FALLBACK_.
    """
    k = _get_key(key)
    pt = plaintext.encode()
    if HAS_CRYPTO:
        nonce = os.urandom(12)
        aes = AESGCM(k)
        ct = aes.encrypt(nonce, pt, None)
        return base64.b64encode(nonce + ct).decode()
    else:
        if os.getenv("ENV") == "production":
            raise RuntimeError(
                "cryptography required in production (insecure fallback disabled)"
            )
        # FALLBACK XOR — INSEGURO, apenas para testes sem cryptography
        enc = bytes(b ^ k[i % len(k)] for i, b in enumerate(pt))
        return FALLBACK_WARNING + ":" + base64.b64encode(enc).decode()


def decrypt_at_rest(token: str, key: str | None = None) -> str:
    """Descriptografa token gerado por encrypt_at_rest."""
    k = _get_key(key)
    if token.startswith(FALLBACK_WARNING + ":"):
        b64 = token.split(":", 1)[1]
        enc = base64.b64decode(b64.encode())
        pt = bytes(b ^ k[i % len(k)] for i, b in enumerate(enc))
        return pt.decode()
    # AESGCM path
    if not HAS_CRYPTO:
        raise ValueError(
            "Token AES-GCM requer 'cryptography' instalada; token não é fallback XOR"
        )
    raw = base64.b64decode(token.encode())
    nonce, ct = raw[:12], raw[12:]
    aes = AESGCM(k)
    pt = aes.decrypt(nonce, ct, None)
    return pt.decode()


# --- Hashing de senhas ---


def hash_password(password: str) -> str:
    """Hash de senha: bcrypt se disponível, senão PBKDF2-HMAC-SHA256."""
    if HAS_BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # fallback PBKDF2
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"pbkdf2$sha256$200000${salt}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
        if not HAS_BCRYPT:
            return False
        return bcrypt.checkpw(password.encode(), hashed.encode())
    if hashed.startswith("pbkdf2$"):
        try:
            _, algo, iters, salt, hexdk = hashed.split("$")
            dk = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), int(iters))
            return hmac.compare_digest(dk.hex(), hexdk)
        except Exception:
            return False
    # legacy sha256 simples (não usar)
    return False


# --- TLS self-check (heurístico) ---


def tls_self_check(host: str = "localhost", port: int = 443) -> Dict[str, str]:
    """
    Checklist estático + tentativa simples de conexão TLS.
    Não substitui ssllabs; apenas guia rápido.
    """
    result: Dict[str, str] = {f"check_{i}": v for i, v in enumerate(TLS_CHECKLIST, 1)}
    # tentativa de socket TLS básica (stdlib)
    try:
        import socket, ssl

        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=3) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                result["tls_negotiated"] = ssock.version() or "unknown"
                cert = ssock.getpeercert()
                result["cert_subject"] = str(cert.get("subject")) if cert else "no cert"
    except Exception as e:
        result["tls_connect"] = (
            f"não conectado ({e}) — verifique se o serviço expõe TLS em {host}:{port}"
        )
    return result


if __name__ == "__main__":
    # smoke
    key = "test-key-123"
    ct = encrypt_at_rest("hello world", key=key)
    print(f"ct={ct[:40]}... backend={'AESGCM' if HAS_CRYPTO else FALLBACK_WARNING}")
    assert decrypt_at_rest(ct, key=key) == "hello world"
    h = hash_password("s3cr3t")
    assert verify_password("s3cr3t", h)
    assert not verify_password("wrong", h)
    print("crypto OK")
    print(TLS_CHECKLIST[0])

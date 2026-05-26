from cryptography.fernet import Fernet
from src.core.config import settings


def _get_fernet() -> Fernet:
    if not settings.fernet_key:
        raise RuntimeError("FERNET_KEY not set. Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    return Fernet(settings.fernet_key.encode())


def encrypt_api_key(plaintext: str) -> bytes:
    f = _get_fernet()
    return f.encrypt(plaintext.encode())


def decrypt_api_key(ciphertext: bytes) -> str:
    f = _get_fernet()
    return f.decrypt(ciphertext).decode()


def get_key_prefix(plaintext: str) -> str:
    if len(plaintext) <= 8:
        return plaintext[:4]
    return f"{plaintext[:4]}...{plaintext[-4:]}"

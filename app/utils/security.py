import hashlib
import hmac
import secrets


def hash_otp(otp: str, secret_key: str) -> str:
    """Hashes the 6-digit OTP using HMAC-SHA256 with the application secret key."""
    return hmac.new(
        secret_key.encode("utf-8"),
        otp.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_otp_hash(otp: str, stored_hash: str, secret_key: str) -> bool:
    """Timing-safe comparison between provided OTP and stored hash."""
    expected_hash = hash_otp(otp, secret_key)
    return hmac.compare_digest(expected_hash, stored_hash)


def generate_otp() -> str:
    """Generates a cryptographically secure 6-digit numerical OTP."""
    num = secrets.randbelow(900000) + 100000
    return str(num)


def generate_random_scratch_code(length: int = 8) -> str:
    """Generates a secure, non-predictable 8-character alphanumeric code."""
    import string
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return "".join(secrets.choice(chars) for _ in range(length))


def generate_verification_token(code: str, phone: str, secret_key: str, expires_in_seconds: int = 600) -> str:
    """
    Generates a cryptographically signed verification token valid for a specified window (default 10 mins).
    Format: {code}:{phone}:{timestamp}:{hmac_signature}
    """
    import time
    ts = int(time.time())
    payload = f"{code.strip()}:{phone.strip()}:{ts}"
    sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_verification_token(token: str, code: str, phone: str, secret_key: str, max_age_seconds: int = 600) -> bool:
    """
    Validates the verification token signature, code/phone binding, and expiration.
    """
    import time
    if not token or ":" not in token:
        return False
    parts = token.strip().split(":")
    if len(parts) != 4:
        return False
    token_code, token_phone, ts_str, sig = parts
    if token_code != code.strip() or token_phone != phone.strip():
        return False
    try:
        ts = int(ts_str)
    except ValueError:
        return False

    now = int(time.time())
    # Expired check (10 min session)
    if (now - ts) > max_age_seconds or ts > (now + 30):
        return False

    expected_payload = f"{token_code}:{token_phone}:{ts}"
    expected_sig = hmac.new(secret_key.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, sig)


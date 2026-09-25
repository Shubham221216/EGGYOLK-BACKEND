import re
from datetime import datetime, timezone
import secrets


def normalize_phone_number(phone: str) -> str:
    """Cleans phone number and extracts 10 digits."""
    if not phone:
        return ""
    # Remove all non-digits
    digits = re.sub(r"\D", "", phone)
    # If 12 digits starting with 91, keep last 10
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def is_valid_indian_phone(phone: str) -> bool:
    """Validates 10-digit Indian mobile number (starts with 6, 7, 8, 9)."""
    norm = normalize_phone_number(phone)
    return bool(re.match(r"^[6-9]\d{9}$", norm))


def mask_phone_number(phone: str) -> str:
    """Masks phone number as 98XXXX3210."""
    norm = normalize_phone_number(phone)
    if len(norm) == 10:
        return f"{norm[:2]}XXXX{norm[-4:]}"
    elif len(norm) > 4:
        return f"{norm[:2]}...{norm[-2:]}"
    return "XXXXXXXXXX"


def generate_reference_id() -> str:
    """Generates unique reference ID: CB-YYYYMMDD-XXXXXX."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_suffix = secrets.token_hex(3).upper()  # 6 hex chars
    return f"CB-{date_str}-{random_suffix}"


def is_valid_8digit_code(code: str) -> bool:
    """Validates whether the cashback code is exactly 8 digits."""
    if not code:
        return False
    clean = code.strip()
    return bool(re.match(r"^\d{8}$", clean))


def is_valid_upi_id(upi: str) -> bool:
    """Validates UPI ID format (e.g. name@bank, mobile@upi)."""
    if not upi:
        return False
    clean = upi.strip()
    return bool(re.match(r"^[a-zA-Z0-9.\-_]{2,100}@[a-zA-Z0-9.\-_]{2,50}$", clean))


def mask_upi_id(upi: str) -> str:
    """Masks UPI ID as adi****@upi."""
    if not upi:
        return ""
    clean = upi.strip()
    if "@" not in clean:
        return f"{clean[:2]}****" if len(clean) >= 2 else "****"
    user_part, handle_part = clean.split("@", 1)
    if len(user_part) <= 3:
        masked_user = f"{user_part}****"
    else:
        masked_user = f"{user_part[:3]}****"
    return f"{masked_user}@{handle_part}"


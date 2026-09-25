from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.utils.helpers import (
    is_valid_8digit_code,
    is_valid_indian_phone,
    normalize_phone_number,
    is_valid_upi_id,
)


class RequestOTPInput(BaseModel):
    code: str = Field(..., description="Unique 8-digit cashback code inside package")
    phone_number: str = Field(..., description="Customer 10-digit mobile number")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip()
        if not is_valid_8digit_code(clean):
            raise ValueError("Invalid cashback code. Please enter exactly 8 digits.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = v.strip()
        if not is_valid_indian_phone(clean):
            raise ValueError("Invalid mobile number. Please enter a valid 10-digit mobile number.")
        return normalize_phone_number(clean)


class RequestOTPResponse(BaseModel):
    success: bool
    message: str
    phone_masked: str
    cooldown_seconds: int
    expires_in_seconds: int
    demo_otp: Optional[str] = None  # Populated in DEMO_MODE for UI display


class VerifyOTPInput(BaseModel):
    code: str = Field(..., description="Unique 8-digit cashback code inside package")
    phone_number: str = Field(..., description="Customer 10-digit mobile number")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit verification OTP")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip()
        if not is_valid_8digit_code(clean):
            raise ValueError("Invalid cashback code. Please enter exactly 8 digits.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = v.strip()
        if not is_valid_indian_phone(clean):
            raise ValueError("Invalid mobile number.")
        return normalize_phone_number(clean)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        clean = v.strip()
        if not (len(clean) == 6 and clean.isdigit()):
            raise ValueError("OTP must be exactly 6 digits.")
        return clean


class VerifyOTPResponse(BaseModel):
    success: bool
    message: str
    verification_token: str
    expires_in_seconds: int = 600


class VerifyClaimInput(BaseModel):
    code: str = Field(..., description="Unique 8-digit cashback code inside package")
    phone_number: str = Field(..., description="Customer 10-digit mobile number")
    otp: Optional[str] = Field(None, min_length=6, max_length=6, description="6-digit verification OTP (optional if verification_token is provided)")
    verification_token: Optional[str] = Field(None, description="Signed server verification token from OTP step")
    upi_id: Optional[str] = Field(None, description="Customer UPI ID")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip()
        if not is_valid_8digit_code(clean):
            raise ValueError("Invalid cashback code. Please enter exactly 8 digits.")
        return clean

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean = v.strip()
        if not is_valid_indian_phone(clean):
            raise ValueError("Invalid mobile number.")
        return normalize_phone_number(clean)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        clean = v.strip()
        if not (len(clean) == 6 and clean.isdigit()):
            raise ValueError("OTP must be exactly 6 digits.")
        return clean

    @field_validator("upi_id")
    @classmethod
    def validate_upi(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        clean = v.strip()
        if not is_valid_upi_id(clean):
            raise ValueError("Invalid UPI ID. Please enter a valid UPI ID (e.g. yourname@upi).")
        return clean


class ClaimResponse(BaseModel):
    success: bool
    message: str
    reference_id: str
    cashback_amount: float
    phone_masked: str
    upi_masked: Optional[str] = None
    claimed_at: datetime
    demo_note: str = "DEMO CASHBACK — NO REAL MONEY WILL BE TRANSFERRED"


class CodeStatusResponse(BaseModel):
    code: str
    status: str
    cashback_amount: float
    expires_at: datetime
    is_expired: bool
    message: Optional[str] = None


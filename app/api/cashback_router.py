from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from app.database.session import get_db
from app.config import get_settings
from app.schemas.cashback import (
    RequestOTPInput,
    RequestOTPResponse,
    VerifyOTPInput,
    VerifyOTPResponse,
    VerifyClaimInput,
    ClaimResponse,
    CodeStatusResponse,
)
from app.services.code_service import CodeService
from app.services.otp_service import OTPService
from app.utils.helpers import mask_phone_number, mask_upi_id
from app.utils.security import verify_verification_token

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/cashback", tags=["Customer Cashback"])
settings = get_settings()


@router.post("/request-otp", response_model=RequestOTPResponse)
def request_otp(payload: RequestOTPInput, db: Session = Depends(get_db)):
    """
    Step 1 of Cashback Claim:
    Validates the 8-digit code, enforces rate limits, generates a 6-digit OTP,
    and returns response with DEMO OTP visible for testing.
    """
    # 1. Validate code state (exists, unused, not expired)
    code_record = CodeService.validate_code_for_otp(db, payload.code)

    # 2. Request OTP with rate-limiting and cooldown enforcement
    raw_otp, otp_record = OTPService.request_otp(db, payload.phone_number, payload.code)

    # In DEMO_MODE, expose demo_otp for user display
    demo_otp_val = raw_otp if settings.DEMO_MODE else None

    return RequestOTPResponse(
        success=True,
        message=f"OTP sent to {mask_phone_number(payload.phone_number)}",
        phone_masked=mask_phone_number(payload.phone_number),
        cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        expires_in_seconds=settings.OTP_EXPIRY_MINUTES * 60,
        demo_otp=demo_otp_val,
    )


@router.post("/verify-otp", response_model=VerifyOTPResponse)
def verify_otp(payload: VerifyOTPInput, db: Session = Depends(get_db)):
    """
    Step 2 of Cashback Claim:
    Verifies the 6-digit OTP and issues a cryptographically signed, short-lived (10-min)
    verification session token bound to the code and phone number.
    """
    token = OTPService.verify_otp_and_issue_token(
        db, payload.phone_number, payload.code, payload.otp
    )
    return VerifyOTPResponse(
        success=True,
        message="OTP verified successfully.",
        verification_token=token,
        expires_in_seconds=600,
    )


@router.post("/claim", response_model=ClaimResponse)
def claim_cashback(payload: VerifyClaimInput, db: Session = Depends(get_db)):
    """
    Final Step of Cashback Claim:
    Validates server-side verification token (or OTP for backward compatibility),
    validates UPI ID, and executes atomic claim to guarantee ONE CODE = ONE CLAIM.
    """
    # 1. Verify authorization via token or OTP
    if payload.verification_token:
        valid_token = verify_verification_token(
            token=payload.verification_token,
            code=payload.code,
            phone=payload.phone_number,
            secret_key=settings.SECRET_KEY,
            max_age_seconds=600  # 10 minutes session
        )
        if not valid_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your verification session has expired or is invalid. Please verify your OTP again."
            )
    elif payload.otp:
        # Backward compatibility for direct claim with OTP
        OTPService.verify_otp(db, payload.phone_number, payload.code, payload.otp)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token or OTP is required to claim cashback."
        )

    # 2. Atomically claim code with UPI ID
    claim = CodeService.atomic_claim_cashback(
        db, payload.code, payload.phone_number, payload.upi_id
    )

    return ClaimResponse(
        success=True,
        message="Cashback request submitted successfully!",
        reference_id=claim.reference_id,
        cashback_amount=claim.cashback_amount,
        phone_masked=mask_phone_number(payload.phone_number),
        upi_masked=mask_upi_id(claim.upi_id) if claim.upi_id else None,
        claimed_at=claim.claimed_at,
        demo_note="DEMO CASHBACK — NO REAL MONEY WILL BE TRANSFERRED",
    )


@router.get("/status/{code}", response_model=CodeStatusResponse)
def get_code_status(code: str, db: Session = Depends(get_db)):
    """Check status of an 8-digit code without claiming."""
    clean_code = code.strip()
    from app.models.cashback_code import CashbackCode
    code_record = db.query(CashbackCode).filter(CashbackCode.code == clean_code).first()
    if not code_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid cashback code. Please check the 8-digit code inside your package."
        )

    return CodeStatusResponse(
        code=code_record.code,
        status=code_record.status,
        cashback_amount=code_record.cashback_amount,
        expires_at=code_record.expires_at,
        is_expired=code_record.is_expired(),
    )

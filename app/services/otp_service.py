from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from fastapi import HTTPException, status
import logging

from app.models.otp_verification import OTPVerification
from app.config import get_settings
from app.utils.security import hash_otp, verify_otp_hash, generate_otp

logger = logging.getLogger("uvicorn.error")
settings = get_settings()


class OTPService:
    @staticmethod
    def request_otp(db: Session, phone_number: str, code: str) -> tuple[str, OTPVerification]:
        """
        Validates rate limiting, creates/refreshes an OTP record,
        logs DEMO OTP to console, and returns (raw_otp, otp_record).
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=settings.RATE_LIMIT_WINDOW_MINUTES)

        # 1. Check rate limit: max requests in window
        recent_requests_count = (
            db.query(func.count(OTPVerification.id))
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.created_at >= window_start
            )
            .scalar()
        )
        if recent_requests_count >= settings.MAX_OTP_REQUESTS_PER_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many OTP requests. Please wait a few minutes before trying again."
            )

        # 2. Check cooldown between resends
        last_otp = (
            db.query(OTPVerification)
            .filter(OTPVerification.phone_number == phone_number)
            .order_by(desc(OTPVerification.created_at))
            .first()
        )
        if last_otp:
            # Check elapsed seconds
            last_created = last_otp.created_at
            if last_created.tzinfo is None:
                last_created = last_created.replace(tzinfo=timezone.utc)
            elapsed = (now - last_created).total_seconds()
            if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
                remaining = int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {remaining} seconds before requesting a new OTP."
                )

        # 3. Generate 6-digit OTP
        raw_otp = generate_otp()
        otp_hash_val = hash_otp(raw_otp, settings.SECRET_KEY)
        expires_at = now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

        # 4. Save OTP record
        otp_record = OTPVerification(
            phone_number=phone_number,
            code=code,
            otp_hash=otp_hash_val,
            attempts=0,
            verified=False,
            created_at=now,
            expires_at=expires_at
        )
        db.add(otp_record)
        db.commit()
        db.refresh(otp_record)

        # 5. Production rule vs DEMO logging:
        # "Also print the OTP in the backend console: [DEMO OTP] Mobile: 9876543210 | OTP: 483921"
        print(f"\n==================================================")
        print(f"[DEMO OTP] Mobile: {phone_number} | OTP: {raw_otp}")
        print(f"==================================================\n", flush=True)
        logger.info(f"[DEMO OTP] Mobile: {phone_number} | OTP: {raw_otp}")

        return raw_otp, otp_record

    @staticmethod
    def verify_otp(db: Session, phone_number: str, code: str, submitted_otp: str) -> OTPVerification:
        """
        Validates OTP against database record.
        Enforces attempt limit, expiration, and code match.
        """
        now = datetime.now(timezone.utc)

        # Retrieve the latest active OTP for this phone & code
        otp_record = (
            db.query(OTPVerification)
            .filter(
                OTPVerification.phone_number == phone_number,
                OTPVerification.code == code,
                OTPVerification.verified == False
            )
            .order_by(desc(OTPVerification.created_at))
            .first()
        )

        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending OTP request found. Please request an OTP first."
            )

        # Check maximum attempts
        if otp_record.attempts >= settings.MAX_OTP_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later."
            )

        # Check expiration
        exp = otp_record.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Your OTP has expired. Please request a new OTP."
            )

        # Verify hash
        is_match = verify_otp_hash(submitted_otp, otp_record.otp_hash, settings.SECRET_KEY)
        if not is_match:
            otp_record.attempts += 1
            db.commit()
            remaining_attempts = settings.MAX_OTP_ATTEMPTS - otp_record.attempts
            if remaining_attempts <= 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please try again later."
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incorrect OTP. Please try again. ({remaining_attempts} attempts remaining)"
            )

        # OTP valid
        otp_record.verified = True
        db.commit()
        return otp_record

    @staticmethod
    def verify_otp_and_issue_token(db: Session, phone_number: str, code: str, submitted_otp: str) -> str:
        """
        Validates OTP against database record, marks it verified, and returns a cryptographically
        signed 10-minute verification token bound to (code, phone_number).
        """
        from app.utils.security import generate_verification_token
        OTPService.verify_otp(db, phone_number, code, submitted_otp)
        token = generate_verification_token(
            code=code,
            phone=phone_number,
            secret_key=settings.SECRET_KEY,
            expires_in_seconds=600  # 10 minutes session
        )
        return token


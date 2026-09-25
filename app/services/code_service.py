from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, update, select
from fastapi import HTTPException, status
from typing import List, Tuple, Optional

from app.models.cashback_code import CashbackCode
from app.models.cashback_claim import CashbackClaim
from app.config import get_settings
from app.utils.security import generate_random_scratch_code
from app.utils.helpers import generate_reference_id

settings = get_settings()


class CodeService:
    @staticmethod
    def validate_code_for_otp(db: Session, code_str: str) -> CashbackCode:
        """
        Validates the cashback code existence, status, and expiry before generating OTP.
        """
        clean_code = code_str.strip()
        code_record = db.query(CashbackCode).filter(CashbackCode.code == clean_code).first()

        if not code_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid cashback code. Please check the 8-digit code inside your package."
            )

        if code_record.status == "USED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This cashback code has already been used."
            )

        if code_record.status == "BLOCKED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This cashback code is currently blocked."
            )

        if code_record.is_expired() or code_record.status == "EXPIRED":
            # Auto update status to EXPIRED if not already
            if code_record.status != "EXPIRED":
                code_record.status = "EXPIRED"
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sorry, this cashback code has expired."
            )

        return code_record

    @staticmethod
    def atomic_claim_cashback(
        db: Session,
        code_str: str,
        phone_number: str,
        upi_id: Optional[str] = None
    ) -> CashbackClaim:
        """
        Guarantees ONE SCRATCH CODE = ONE CASHBACK CLAIM.
        Uses an atomic conditional UPDATE at the database level inside a transaction.
        Even with concurrent requests, only one query can update status from 'UNUSED' to 'USED'.
        """
        clean_code = code_str.strip()
        now = datetime.now(timezone.utc)

        # 1. Fetch code record with preliminary check
        code_record = db.query(CashbackCode).filter(CashbackCode.code == clean_code).first()
        if not code_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid cashback code. Please check the 8-digit code inside your package."
            )

        if code_record.status == "USED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This cashback code has already been used."
            )

        if code_record.is_expired() or code_record.status == "EXPIRED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sorry, this cashback code has expired."
            )

        # 2. Atomic conditional update to eliminate race conditions
        # Only rows where id == code_record.id AND status == 'UNUSED' will be updated
        stmt = (
            update(CashbackCode)
            .where(
                CashbackCode.id == code_record.id,
                CashbackCode.status == "UNUSED"
            )
            .values(
                status="USED",
                used_at=now
            )
        )
        result = db.execute(stmt)

        # If 0 rows were updated, a simultaneous request already marked it USED
        if result.rowcount == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This cashback code has already been used."
            )

        # 3. Create the claim record with database unique constraint on cashback_code_id
        ref_id = generate_reference_id()
        claim = CashbackClaim(
            cashback_code_id=code_record.id,
            phone_number=phone_number,
            cashback_amount=code_record.cashback_amount,
            status="SUCCESS",
            reference_id=ref_id,
            upi_id=upi_id.strip() if upi_id else None,
            claimed_at=now
        )
        db.add(claim)

        try:
            db.commit()
            db.refresh(claim)
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This cashback code has already been used."
            )

        return claim

    @staticmethod
    def generate_batch_codes(
        db: Session,
        count: int = 10,
        cashback_amount: float = 20.0,
        expires_days: int = 30,
        campaign_id: str = "CAMPAIGN_2026_EGG"
    ) -> List[CashbackCode]:
        """Generates N unique random alphanumeric codes in batch."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_days)

        existing_codes_set = set(
            row[0] for row in db.query(CashbackCode.code).all()
        )

        new_codes: List[CashbackCode] = []
        generated_set = set()

        while len(new_codes) < count:
            code_candidate = generate_random_scratch_code()
            if code_candidate not in existing_codes_set and code_candidate not in generated_set:
                generated_set.add(code_candidate)
                new_codes.append(
                    CashbackCode(
                        code=code_candidate,
                        cashback_amount=cashback_amount,
                        status="UNUSED",
                        campaign_id=campaign_id,
                        created_at=now,
                        expires_at=expires_at
                    )
                )

        db.add_all(new_codes)
        db.commit()
        return new_codes

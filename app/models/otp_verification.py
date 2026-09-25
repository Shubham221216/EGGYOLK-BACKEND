from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Index
from app.database.session import Base


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), index=True, nullable=False)
    code = Column(String(8), index=True, nullable=False)
    otp_hash = Column(String(128), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_otp_phone_code", "phone_number", "code"),
    )

    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now > exp

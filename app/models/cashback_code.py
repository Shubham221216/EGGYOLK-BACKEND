from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.orm import relationship
from app.database.session import Base


class CashbackCode(Base):
    __tablename__ = "cashback_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(8), unique=True, index=True, nullable=False)
    cashback_amount = Column(Float, default=20.0, nullable=False)
    status = Column(String(20), default="UNUSED", index=True, nullable=False)  # UNUSED, USED, EXPIRED, BLOCKED
    campaign_id = Column(String(50), default="CAMPAIGN_2026_EGG", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)

    # 1-to-1 relationship with claim
    claim = relationship("CashbackClaim", back_populates="cashback_code", uselist=False)

    __table_args__ = (
        Index("idx_code_status", "code", "status"),
    )

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        # Normalize timezone comparison
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now > exp

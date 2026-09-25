from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database.session import Base


class CashbackClaim(Base):
    __tablename__ = "cashback_claims"

    id = Column(Integer, primary_key=True, index=True)
    cashback_code_id = Column(Integer, ForeignKey("cashback_codes.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True)
    phone_number = Column(String(20), index=True, nullable=False)
    cashback_amount = Column(Float, nullable=False)
    status = Column(String(20), default="SUCCESS", nullable=False)  # SUCCESS, FAILED
    reference_id = Column(String(50), unique=True, index=True, nullable=False)
    upi_id = Column(String(100), nullable=True)
    claimed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cashback_code = relationship("CashbackCode", back_populates="claim")

    __table_args__ = (
        UniqueConstraint("cashback_code_id", name="uq_cashback_code_claim"),
        Index("idx_claims_phone_status", "phone_number", "status"),
    )

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class GenerateCodesInput(BaseModel):
    count: int = Field(default=10, ge=1, le=10000, description="Number of unique scratch codes to generate")
    cashback_amount: float = Field(default=20.0, gt=0, description="Cashback amount per code in INR")
    expires_days: int = Field(default=30, ge=1, le=365, description="Validity period in days from now")
    campaign_id: Optional[str] = Field(default="CAMPAIGN_2026_EGG", description="Campaign identifier")


class GenerateCodesResponse(BaseModel):
    success: bool
    generated_count: int
    message: str
    sample_codes: List[str]


class DashboardStats(BaseModel):
    total_codes: int
    unused_codes: int
    used_codes: int
    expired_codes: int
    total_claims: int
    total_cashback_amount: float
    campaign_name: str


class CodeItem(BaseModel):
    id: int
    code: str
    status: str
    cashback_amount: float
    created_at: datetime
    expires_at: datetime
    used_at: Optional[datetime] = None
    phone_number: Optional[str] = None
    phone_masked: Optional[str] = None
    reference_id: Optional[str] = None


class ClaimItem(BaseModel):
    id: int
    reference_id: str
    code: str
    phone_number: Optional[str] = None
    phone_masked: str
    upi_masked: Optional[str] = None
    cashback_amount: float
    status: str
    claimed_at: datetime


class SearchResult(BaseModel):
    codes: List[CodeItem]
    claims: List[ClaimItem]

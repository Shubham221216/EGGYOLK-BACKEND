import io
import csv
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from typing import Optional, List

from app.database.session import get_db
from app.config import get_settings
from app.models.cashback_code import CashbackCode
from app.models.cashback_claim import CashbackClaim
from app.schemas.admin import (
    GenerateCodesInput,
    GenerateCodesResponse,
    DashboardStats,
    CodeItem,
    ClaimItem,
    SearchResult,
)
from app.services.code_service import CodeService
from app.services.qr_service import QRService
from app.utils.helpers import mask_phone_number, mask_upi_id

router = APIRouter(prefix="/api/admin", tags=["Admin Portal"])
settings = get_settings()


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Provides overall campaign metrics and code breakdown."""
    total_codes = db.query(func.count(CashbackCode.id)).scalar() or 0
    unused_codes = db.query(func.count(CashbackCode.id)).filter(CashbackCode.status == "UNUSED").scalar() or 0
    used_codes = db.query(func.count(CashbackCode.id)).filter(CashbackCode.status == "USED").scalar() or 0
    expired_codes = db.query(func.count(CashbackCode.id)).filter(CashbackCode.status == "EXPIRED").scalar() or 0

    total_claims = db.query(func.count(CashbackClaim.id)).scalar() or 0
    total_cashback = db.query(func.sum(CashbackClaim.cashback_amount)).filter(CashbackClaim.status == "SUCCESS").scalar() or 0.0

    return DashboardStats(
        total_codes=total_codes,
        unused_codes=unused_codes,
        used_codes=used_codes,
        expired_codes=expired_codes,
        total_claims=total_claims,
        total_cashback_amount=float(total_cashback),
        campaign_name=settings.CAMPAIGN_NAME,
    )


@router.post("/codes/generate", response_model=GenerateCodesResponse)
def generate_codes(payload: GenerateCodesInput, db: Session = Depends(get_db)):
    """Generates a batch of unique random alphanumeric scratch codes."""
    codes = CodeService.generate_batch_codes(
        db=db,
        count=payload.count,
        cashback_amount=payload.cashback_amount,
        expires_days=payload.expires_days,
        campaign_id=payload.campaign_id or settings.CAMPAIGN_ID,
    )
    samples = [c.code for c in codes[:5]]
    return GenerateCodesResponse(
        success=True,
        generated_count=len(codes),
        message=f"Successfully generated {len(codes)} codes.",
        sample_codes=samples,
    )


@router.get("/codes", response_model=List[CodeItem])
def list_codes(
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists codes with optional status filtering and search query."""
    query = db.query(CashbackCode)

    if status and status.upper() != "ALL":
        query = query.filter(CashbackCode.status == status.upper())

    if search:
        query = query.filter(CashbackCode.code.contains(search.strip()))

    codes = query.order_by(desc(CashbackCode.created_at)).offset(offset).limit(limit).all()

    result = []
    for c in codes:
        phone_raw = c.claim.phone_number if c.claim else None
        phone_masked = mask_phone_number(c.claim.phone_number) if c.claim else None
        ref_id = c.claim.reference_id if c.claim else None
        result.append(
            CodeItem(
                id=c.id,
                code=c.code,
                status=c.status,
                cashback_amount=c.cashback_amount,
                created_at=c.created_at,
                expires_at=c.expires_at,
                used_at=c.used_at,
                phone_number=phone_raw,
                phone_masked=phone_masked,
                reference_id=ref_id,
            )
        )
    return result


@router.get("/claims", response_model=List[ClaimItem])
def list_claims(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists recent claims with full phone numbers and masked UPI."""
    query = db.query(CashbackClaim).join(CashbackCode)

    if status and status.upper() != "ALL":
        query = query.filter(CashbackClaim.status == status.upper())

    claims = query.order_by(desc(CashbackClaim.claimed_at)).offset(offset).limit(limit).all()

    return [
        ClaimItem(
            id=cl.id,
            reference_id=cl.reference_id,
            code=cl.cashback_code.code,
            phone_number=cl.phone_number,
            phone_masked=mask_phone_number(cl.phone_number),
            upi_masked=mask_upi_id(cl.upi_id) if cl.upi_id else None,
            cashback_amount=cl.cashback_amount,
            status=cl.status,
            claimed_at=cl.claimed_at,
        )
        for cl in claims
    ]


@router.get("/search", response_model=SearchResult)
def search_system(query: str = Query(..., min_length=2), db: Session = Depends(get_db)):
    """Search by scratch code, phone number, or reference ID."""
    clean = query.strip()

    # Search codes
    code_matches = (
        db.query(CashbackCode)
        .filter(CashbackCode.code.contains(clean))
        .limit(20)
        .all()
    )

    code_items = [
        CodeItem(
            id=c.id,
            code=c.code,
            status=c.status,
            cashback_amount=c.cashback_amount,
            created_at=c.created_at,
            expires_at=c.expires_at,
            used_at=c.used_at,
            phone_number=c.claim.phone_number if c.claim else None,
            phone_masked=mask_phone_number(c.claim.phone_number) if c.claim else None,
            reference_id=c.claim.reference_id if c.claim else None,
        )
        for c in code_matches
    ]

    # Search claims by reference ID, phone, or UPI
    claim_matches = (
        db.query(CashbackClaim)
        .join(CashbackCode)
        .filter(
            or_(
                CashbackClaim.reference_id.ilike(f"%{clean}%"),
                CashbackClaim.phone_number.contains(clean),
                CashbackClaim.upi_id.ilike(f"%{clean}%")
            )
        )
        .limit(20)
        .all()
    )

    claim_items = [
        ClaimItem(
            id=cl.id,
            reference_id=cl.reference_id,
            code=cl.cashback_code.code,
            phone_number=cl.phone_number,
            phone_masked=mask_phone_number(cl.phone_number),
            upi_masked=mask_upi_id(cl.upi_id) if cl.upi_id else None,
            cashback_amount=cl.cashback_amount,
            status=cl.status,
            claimed_at=cl.claimed_at,
        )
        for cl in claim_matches
    ]

    return SearchResult(codes=code_items, claims=claim_items)


@router.get("/export/codes")
def export_codes_csv(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Exports codes as downloadable CSV file (code,cashback_amount,expires_at,status)."""
    query = db.query(CashbackCode)
    if status and status.upper() != "ALL":
        query = query.filter(CashbackCode.status == status.upper())

    codes = query.order_by(desc(CashbackCode.created_at)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["code", "cashback_amount", "expires_at", "status"])

    for c in codes:
        writer.writerow([
            c.code,
            f"{c.cashback_amount:.2f}",
            c.expires_at.strftime("%Y-%m-%d"),
            c.status
        ])

    output.seek(0)
    filename = f"cashback_codes_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/claims")
def export_claims_csv(db: Session = Depends(get_db)):
    """Exports claims as downloadable CSV with full phone and masked UPI."""
    claims = db.query(CashbackClaim).join(CashbackCode).order_by(desc(CashbackClaim.claimed_at)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["reference_id", "code", "phone_number", "upi_masked", "cashback_amount", "status", "claimed_at"])

    for cl in claims:
        writer.writerow([
            cl.reference_id,
            cl.cashback_code.code,
            cl.phone_number,
            mask_upi_id(cl.upi_id) if cl.upi_id else "",
            f"{cl.cashback_amount:.2f}",
            cl.status,
            cl.claimed_at.strftime("%Y-%m-%d %H:%M:%S")
        ])

    output.seek(0)
    filename = f"cashback_claims_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/qr")
def get_campaign_qr(destination_url: Optional[str] = None):
    """Returns campaign packaging QR code image (PNG)."""
    png_bytes = QRService.generate_campaign_qr_png(destination_url)
    return Response(content=png_bytes, media_type="image/png")

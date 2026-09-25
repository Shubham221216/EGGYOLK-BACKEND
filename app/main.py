from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import get_settings
from app.database.session import Base, engine, SessionLocal
from app.models.cashback_code import CashbackCode
from app.models.cashback_claim import CashbackClaim
from app.api.cashback_router import router as cashback_router
from app.api.admin_router import router as admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("egg_cashback")
settings = get_settings()


def seed_demo_data():
    """
    - GY7K9P2A -> UNUSED (Scenario A)
    - EGG24X91 -> UNUSED
    - YOLK8F72 -> USED (Scenario B / sample claim)
    - EXPIRE99 -> EXPIRED (Scenario C)
    Invalid code: INV4L1DX (Scenario D - left absent from DB)
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        future_expiry = now + timedelta(days=settings.DEFAULT_EXPIRY_DAYS)
        past_expiry = now - timedelta(days=15)

        seeds = [
            # 1. Scenario A: Unused fresh code
            {
                "code": "GY7K9P2A",
                "amount": settings.DEFAULT_CASHBACK_AMOUNT,
                "status": "UNUSED",
                "expires_at": future_expiry,
                "claimed": False,
            },
            # 2. Unused fresh code
            {
                "code": "EGG24X91",
                "amount": settings.DEFAULT_CASHBACK_AMOUNT,
                "status": "UNUSED",
                "expires_at": future_expiry,
                "claimed": False,
            },
            # 3. Scenario B / Demo used code
            {
                "code": "YOLK8F72",
                "amount": settings.DEFAULT_CASHBACK_AMOUNT,
                "status": "USED",
                "expires_at": future_expiry,
                "claimed": True,
                "claim_phone": "9876543210",
                "claim_ref": "CB-20260924-000001",
            },
            # 4. Scenario C: Expired code
            {
                "code": "EXPIRE99",
                "amount": settings.DEFAULT_CASHBACK_AMOUNT,
                "status": "EXPIRED",
                "expires_at": past_expiry,
                "claimed": False,
            },
        ]

        for s in seeds:
            existing = db.query(CashbackCode).filter(CashbackCode.code == s["code"]).first()
            if not existing:
                code_obj = CashbackCode(
                    code=s["code"],
                    cashback_amount=s["amount"],
                    status=s["status"],
                    campaign_id=settings.CAMPAIGN_ID,
                    created_at=now,
                    expires_at=s["expires_at"],
                    used_at=now if s["claimed"] else None,
                )
                db.add(code_obj)
                db.flush()

                if s.get("claimed"):
                    claim_obj = CashbackClaim(
                        cashback_code_id=code_obj.id,
                        phone_number=s["claim_phone"],
                        cashback_amount=s["amount"],
                        status="SUCCESS",
                        reference_id=s["claim_ref"],
                        claimed_at=now,
                    )
                    db.add(claim_obj)

        db.commit()
        logger.info("Demo seed data verified and ready.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding demo data: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    logger.info("Initializing database schema...")
    Base.metadata.create_all(bind=engine)

    # Check and migrate upi_id column in cashback_claims if not present (for SQLite)
    try:
        with engine.connect() as conn:
            cursor = conn.connection.cursor()
            cursor.execute("PRAGMA table_info(cashback_claims)")
            columns = [col[1] for col in cursor.fetchall()]
            if "upi_id" not in columns:
                logger.info("Migrating cashback_claims table: adding upi_id column...")
                cursor.execute("ALTER TABLE cashback_claims ADD COLUMN upi_id VARCHAR(100)")
                conn.connection.commit()
    except Exception as e:
        logger.warning(f"Note on DB schema check: {e}")

    # Seed demo data
    seed_demo_data()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for GoldenYolk Farms Egg Product Packaging Cashback System",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(cashback_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {
        "app": settings.APP_NAME,
        "status": "online",
        "demo_mode": settings.DEMO_MODE,
        "campaign": settings.CAMPAIGN_NAME,
        "docs_url": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone

from app.database.session import Base, get_db
from app.main import app, seed_demo_data
from app.models.cashback_code import CashbackCode
from app.models.cashback_claim import CashbackClaim

# Use an in-memory SQLite database with StaticPool so all sessions share the tables
from sqlalchemy.pool import StaticPool

TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=30)
    past = now - timedelta(days=15)

    # Seed initial test data
    c1 = CashbackCode(code="58392147", cashback_amount=20.0, status="UNUSED", expires_at=future)
    c2 = CashbackCode(code="71938452", cashback_amount=20.0, status="UNUSED", expires_at=future)
    c3 = CashbackCode(code="24681735", cashback_amount=20.0, status="USED", expires_at=future, used_at=now)
    c4 = CashbackCode(code="13579246", cashback_amount=20.0, status="EXPIRED", expires_at=past)
    db.add_all([c1, c2, c3, c4])
    db.flush()

    claim3 = CashbackClaim(
        cashback_code_id=c3.id,
        phone_number="9876543210",
        cashback_amount=20.0,
        status="SUCCESS",
        reference_id="CB-20260924-000001",
        claimed_at=now,
    )
    db.add(claim3)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


def test_scenario_a_successful_claim():
    """Scenario A: Fresh code 58392147 + 9876543210 -> Success."""
    # 1. Request OTP
    req_res = client.post("/api/cashback/request-otp", json={
        "code": "58392147",
        "phone_number": "9876543210"
    })
    assert req_res.status_code == 200
    data = req_res.json()
    assert data["success"] is True
    assert data["demo_otp"] is not None
    demo_otp = data["demo_otp"]

    # 2. Claim with correct OTP
    claim_res = client.post("/api/cashback/claim", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "otp": demo_otp
    })
    assert claim_res.status_code == 200
    claim_data = claim_res.json()
    assert claim_data["success"] is True
    assert claim_data["cashback_amount"] == 20.0
    assert claim_data["phone_masked"] == "98XXXX3210"
    assert claim_data["reference_id"].startswith("CB-")


def test_scenario_b_duplicate_code_different_mobile():
    """Scenario B: Once code 58392147 is claimed, a different mobile tries -> Rejected!"""
    # 1. First claim succeeds
    req_res = client.post("/api/cashback/request-otp", json={
        "code": "58392147",
        "phone_number": "9876543210"
    })
    assert req_res.status_code == 200
    demo_otp = req_res.json()["demo_otp"]

    claim_res = client.post("/api/cashback/claim", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "otp": demo_otp
    })
    assert claim_res.status_code == 200

    # 2. Second customer with different phone tries the same code
    dup_res = client.post("/api/cashback/request-otp", json={
        "code": "58392147",
        "phone_number": "9123456789"
    })
    assert dup_res.status_code == 400
    assert "already been used" in dup_res.json()["detail"].lower()

    # Also test directly attempting claim
    dup_claim = client.post("/api/cashback/claim", json={
        "code": "58392147",
        "phone_number": "9123456789",
        "otp": "123456"
    })
    assert dup_claim.status_code in [400, 404]


def test_scenario_c_expired_code():
    """Scenario C: Code 13579246 is expired -> Rejected!"""
    res = client.post("/api/cashback/request-otp", json={
        "code": "13579246",
        "phone_number": "9876543210"
    })
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


def test_scenario_d_invalid_code():
    """Scenario D: Code 11111111 does not exist -> Rejected!"""
    res = client.post("/api/cashback/request-otp", json={
        "code": "11111111",
        "phone_number": "9876543210"
    })
    assert res.status_code == 404
    assert "invalid cashback code" in res.json()["detail"].lower()


def test_invalid_otp():
    """Entering wrong OTP returns clear error and increments attempts."""
    req_res = client.post("/api/cashback/request-otp", json={
        "code": "71938452",
        "phone_number": "9876543210"
    })
    assert req_res.status_code == 200

    bad_claim = client.post("/api/cashback/claim", json={
        "code": "71938452",
        "phone_number": "9876543210",
        "otp": "000000"
    })
    assert bad_claim.status_code == 400
    assert "incorrect otp" in bad_claim.json()["detail"].lower()


def test_admin_dashboard_and_generate():
    """Tests admin dashboard statistics and code generation."""
    # Check stats
    stats_res = client.get("/api/admin/dashboard")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_codes"] >= 4
    assert stats["used_codes"] >= 1
    assert stats["expired_codes"] >= 1

    # Generate 50 codes
    gen_res = client.post("/api/admin/codes/generate", json={
        "count": 50,
        "cashback_amount": 20.0,
        "expires_days": 45
    })
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert gen_data["generated_count"] == 50

    # Verify CSV export works
    csv_res = client.get("/api/admin/export/codes")
    assert csv_res.status_code == 200
    assert "code,cashback_amount,expires_at,status" in csv_res.text


def test_concurrent_double_claim_race_condition():
    """Verify that when a code is claimed, subsequent attempts are rejected at OTP and atomic DB levels."""
    # 1. Request OTP for fresh code 71938452
    req1 = client.post("/api/cashback/request-otp", json={
        "code": "71938452",
        "phone_number": "9876543210"
    })
    assert req1.status_code == 200
    otp1 = req1.json()["demo_otp"]

    # First claim succeeds
    res1 = client.post("/api/cashback/claim", json={
        "code": "71938452",
        "phone_number": "9876543210",
        "otp": otp1
    })
    assert res1.status_code == 200
    assert res1.json()["success"] is True

    # 2. Trying to reuse the same OTP is rejected
    res2 = client.post("/api/cashback/claim", json={
        "code": "71938452",
        "phone_number": "9876543210",
        "otp": otp1
    })
    assert res2.status_code == 400

    # 3. Trying to request a new OTP for the already-used code is strictly rejected
    req2 = client.post("/api/cashback/request-otp", json={
        "code": "71938452",
        "phone_number": "9123456789"
    })
    assert req2.status_code == 400
    assert "already been used" in req2.json()["detail"].lower()

    # 4. Direct atomic database-level test: calling atomic_claim_cashback directly must fail
    from app.services.code_service import CodeService
    from fastapi import HTTPException
    db = TestingSessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        CodeService.atomic_claim_cashback(db, "71938452", "9998887776")
    assert "already been used" in exc_info.value.detail.lower()
    db.close()


def test_verify_otp_and_claim_with_token_and_upi():
    """Tests the new 5-step customer flow: Request OTP -> Verify OTP -> Receive Token -> Submit Claim with UPI."""
    # 1. Request OTP for code 58392147
    req_res = client.post("/api/cashback/request-otp", json={
        "code": "58392147",
        "phone_number": "9876543210"
    })
    assert req_res.status_code == 200
    demo_otp = req_res.json()["demo_otp"]

    # 2. Verify OTP standalone to get server verification token
    verify_res = client.post("/api/cashback/verify-otp", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "otp": demo_otp
    })
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["success"] is True
    assert "verification_token" in verify_data
    token = verify_data["verification_token"]

    # 3. Submit claim with verification token and UPI ID
    claim_res = client.post("/api/cashback/claim", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "verification_token": token,
        "upi_id": "adi@upi"
    })
    assert claim_res.status_code == 200
    claim_data = claim_res.json()
    assert claim_data["success"] is True
    assert claim_data["upi_masked"] == "adi****@upi"
    assert claim_data["phone_masked"] == "98XXXX3210"


def test_invalid_upi_rejected():
    """Verify that malformed UPI IDs are strictly rejected."""
    req_res = client.post("/api/cashback/request-otp", json={
        "code": "58392147",
        "phone_number": "9876543210"
    })
    assert req_res.status_code == 200
    demo_otp = req_res.json()["demo_otp"]

    verify_res = client.post("/api/cashback/verify-otp", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "otp": demo_otp
    })
    assert verify_res.status_code == 200
    token = verify_res.json()["verification_token"]

    # Invalid UPI
    bad_claim = client.post("/api/cashback/claim", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "verification_token": token,
        "upi_id": "invalid_upi_without_at"
    })
    assert bad_claim.status_code == 422  # Pydantic validation error


def test_tampered_or_invalid_verification_token_rejected():
    """Verify that forged/tampered verification tokens are rejected."""
    bad_claim = client.post("/api/cashback/claim", json={
        "code": "58392147",
        "phone_number": "9876543210",
        "verification_token": "58392147:9876543210:1234567890:tampered_signature",
        "upi_id": "adi@upi"
    })
    assert bad_claim.status_code == 400
    assert "verification session has expired or is invalid" in bad_claim.json()["detail"].lower()


import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.repository import get_repository
from app.seed import seed_database
from app.security import create_worker_session_token, create_admin_session_token


@pytest.fixture(autouse=True)
def init_test_db():
    repo = get_repository()
    seed_database(repo)


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "FairShift"


def test_admin_auth_required():
    client = TestClient(app)
    # Attempt to access admin overview without auth
    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 401
    assert "error" in response.json()
    assert response.json()["error"]["code"] == "HTTP_401"


def test_admin_login_success():
    client = TestClient(app)
    response = client.post("/api/v1/admin/login", json={"pin": "4821"})
    assert response.status_code == 200
    assert "admin_session" in response.cookies
    assert response.json()["status"] == "ok"


def test_worker_auth_required():
    client = TestClient(app)
    # Attempt to check-in without auth cookie
    response = client.post("/api/v1/worker/check-in", json={})
    assert response.status_code == 401
    assert "error" in response.json()


def test_invalid_input_rejected():
    client = TestClient(app)
    # PIN too short (< 4 chars)
    response = client.post("/api/v1/worker/login", json={"phone": "9876543210", "pin": "12"})
    assert response.status_code == 422  # Pydantic validation error

    # Phone empty
    response = client.post("/api/v1/worker/login", json={"phone": "", "pin": "1234"})
    assert response.status_code == 422


def test_feedback_stores_no_worker_id():
    client = TestClient(app)
    repo = get_repository()

    # Log in as worker Rajesh (w-1)
    token = create_worker_session_token("w-1")
    client.cookies.set("worker_session", token)

    initial_feedback_count = len(repo.feedbacks)

    feedback_payload = {
        "site_id": "site-construction",
        "manager_rating": 4,
        "conditions_rating": 5,
        "comment": "Safe hydration stations provided throughout hot afternoon shift."
    }

    response = client.post("/api/v1/worker/feedback", json=feedback_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify repository storage
    assert len(repo.feedbacks) == initial_feedback_count + 1
    new_entry = repo.feedbacks[-1]

    # CRITICAL SECURITY ASSERTION: worker_id must NOT exist on AnonymousFeedback model
    assert not hasattr(new_entry, "worker_id")
    feedback_dict = new_entry.model_dump()
    assert "worker_id" not in feedback_dict
    assert feedback_dict["site_id"] == "site-construction"
    assert feedback_dict["manager_rating"] == 4
    assert feedback_dict["conditions_rating"] == 5


def test_public_passport_endpoint():
    client = TestClient(app)
    # Fetch pre-seeded passport for Rajesh Kumar
    response = client.get("/api/v1/passport/pass-rajesh-k892")
    assert response.status_code == 200
    data = response.json()
    assert data["worker_name"] == "Rajesh Kumar"
    assert "OSHA 30h Certified" in data["verified_badges"]

    # Non-existent passport returns 404
    bad_res = client.get("/api/v1/passport/pass-non-existent-xyz")
    assert bad_res.status_code == 404


def test_ai_mocked_safety_report_triage():
    client = TestClient(app)
    token = create_worker_session_token("w-1")
    client.cookies.set("worker_session", token)

    mock_gemini_json = '{"category": "hazard", "severity": "critical", "summary_en": "Critical scaffold clamp failure", "summary_local": "சாரக்கட்டு கிளாம்புகள் தளர்வாக உள்ளன"}'

    with patch("app.services.ai._execute_gemini_call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_gemini_json

        response = client.post(
            "/api/v1/worker/safety-reports",
            json={"input_text": "Scaffold clamp broken on high tower", "language": "ta"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "hazard"
        assert data["severity"] == "critical"
        assert data["summary_en"] == "Critical scaffold clamp failure"
        assert data["status"] == "Reported"

from fastapi.testclient import TestClient

from src.api.app import app


client = TestClient(app)


def test_foreign_origin_is_not_reflected():
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"


def test_allowlisted_origin_passes_preflight():
    r = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert r.headers["access-control-allow-credentials"] == "true"


def test_cors_origins_env_override():
    from src.core.config import Settings

    settings = Settings(cors_origins="http://localhost:5173")
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    assert origins == ["http://localhost:5173"]

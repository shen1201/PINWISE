"""Offline integration test for the future HTTPS origin; no tunnel or APIs called."""
import json
import os
import tempfile


def main():
    origin = "https://finpilot-test.example.org"
    with tempfile.TemporaryDirectory(prefix="finpilot-p3-security-") as directory:
        os.environ.update({
            "FINPILOT_SKIP_DOTENV": "1", "GEMINI_API_KEY": "", "FINPILOT_GEMINI_ENABLED": "false",
            "FINPILOT_PREVIEW_FIXTURE_MODE": "false", "FINPILOT_PREVIEW_AUTH_REQUIRED": "false",
            "FINPILOT_DEMO_ACCESS_ENABLED": "true", "FINPILOT_CORS_ORIGINS": origin,
            "FINPILOT_DEMO_SESSION_SECRET": "offline-test-only-secret-more-than-32-characters",
            "FINPILOT_DEMO_INVITE_TOKEN": "offline-test-only-invite", "FINPILOT_DEMO_EXPIRES_AT": "0",
            "FINPILOT_DATA_DIR": directory, "SHIOAJI_ENABLED": "false", "FINPILOT_STARTUP_SOURCE_CHECK": "false",
            "FINPILOT_DAILY_GEMINI_CALL_LIMIT": "0", "FINPILOT_VISITOR_DAILY_GEMINI_CALL_LIMIT": "0",
        })
        from fastapi.testclient import TestClient
        from backend.app.main import app
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 200
            assert client.get("/api/health").status_code == 401
            assert client.post("/api/demo/session", headers={"Origin": origin}).status_code == 403
            headers = {"Origin": origin, "X-FinPilot-Invite": "offline-test-only-invite"}
            assert client.post("/api/demo/session", headers={**headers, "Origin": "https://attacker.example"}).status_code == 403
            response = client.post("/api/demo/session", headers=headers)
            assert response.status_code == 200
            auth = {"Authorization": "Bearer " + response.json()["access_token"]}
            health = client.get("/api/health", headers=auth)
            assert health.status_code == 200 and health.json()["data_mode"] == "live"
            rows = client.get("/api/sources/status", headers=auth).json()
            assert len(rows) == 9
            assert next(row for row in rows if row["source"] == "Gemini")["configuration_status"] in {"missing", "disabled"}
            for path in ("/docs", "/openapi.json", "/redoc", "/.env", "/backend/", "/qa/", "/docs/acceptance/p3/live-api.json"):
                assert client.get(path, headers=auth).status_code == 404, path
            runtime = client.get("/runtime-config.js").text
            assert '"inviteRequired": true' in runtime
            assert "offline-test-only" not in runtime
            assert client.get("/").status_code == 200
    print(json.dumps({"checks": 18, "status": "pass", "real_gemini_calls": 0, "external_requests": 0, "scope": "in-process protected origin, not remote HTTPS acceptance"}))


if __name__ == "__main__":
    main()

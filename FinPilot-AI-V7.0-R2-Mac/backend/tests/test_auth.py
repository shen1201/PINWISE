from __future__ import annotations

import os
import unittest

os.environ["FINPILOT_SKIP_DOTENV"] = "1"

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.app.storage.auth import AccountError, AccountSessionMiddleware, hash_password, validate_credentials, verify_password
from backend.app.security.preview_security import current_visitor_id


class PasswordTests(unittest.TestCase):
    def test_hash_is_salted_and_verifies(self):
        first, second = hash_password("correct horse"), hash_password("correct horse")
        self.assertNotEqual(first, second, "相同密碼應產生不同雜湊（每次不同 salt）")
        self.assertNotIn("correct horse", first)
        self.assertTrue(verify_password("correct horse", first))
        self.assertFalse(verify_password("wrong horse!", first))
        self.assertFalse(verify_password("anything", "not-a-valid-hash"))

    def test_credentials_are_validated_and_username_lowercased(self):
        self.assertEqual(validate_credentials(" Alice_01 ", "12345678"), "alice_01")
        for username, password in (("ab", "12345678"), ("bad name", "12345678"), ("a" * 33, "12345678"),
                                   ("alice", "1234567"), ("alice", "x" * 129)):
            with self.subTest(username=username, password_length=len(password)):
                with self.assertRaises(AccountError):
                    validate_credentials(username, password)


class FakeAccounts:
    async def resolve(self, token):
        if token == "valid-token":
            return {"id": 7, "username": "alice", "owner_id": "user:7"}
        return None


def make_client(accounts):
    app = FastAPI()
    app.add_middleware(AccountSessionMiddleware, accounts=accounts)

    @app.get("/api/whoami")
    async def whoami(request: Request):
        return {"visitor": request.scope.get("finpilot.visitor_id", "local"), "context": current_visitor_id.get()}

    @app.get("/api/auth/me")
    async def me(request: Request):
        return {"user": request.scope.get("finpilot.user")}

    return TestClient(app)


class SessionMiddlewareTests(unittest.TestCase):
    def test_valid_session_uses_account_owner_id(self):
        response = make_client(FakeAccounts()).get("/api/whoami", headers={"X-FinPilot-Session": "valid-token"})
        self.assertEqual(response.json(), {"visitor": "user:7", "context": "user:7"})

    def test_guest_request_is_unchanged(self):
        self.assertEqual(make_client(FakeAccounts()).get("/api/whoami").json()["visitor"], "local")

    def test_invalid_session_is_rejected_instead_of_falling_back_to_guest(self):
        response = make_client(FakeAccounts()).get("/api/whoami", headers={"X-FinPilot-Session": "expired"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "account_session_invalid")

    def test_auth_routes_tolerate_invalid_session(self):
        response = make_client(FakeAccounts()).get("/api/auth/me", headers={"X-FinPilot-Session": "expired"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["user"])

    def test_without_database_header_is_ignored(self):
        response = make_client(None).get("/api/whoami", headers={"X-FinPilot-Session": "valid-token"})
        self.assertEqual(response.json()["visitor"], "local")


if __name__ == "__main__":
    unittest.main()

import pytest

from app import create_app
from app.db import connect
from app.services import accounts
from tests.conftest import TestConfig, make_client

PW = "correct-horse-battery"


@pytest.fixture()
def ac(db_url):
    return make_client(db_url)


def test_register_login_logout_me(ac):
    assert ac.get("/api/auth/me").get_json()["user"] is None
    uid = ac.register("a@example.com")
    assert ac.get("/api/auth/me").get_json()["user"]["email"] == "a@example.com"
    ac.logout()
    assert ac.get("/api/auth/me").get_json()["user"] is None
    ac.login("A@Example.com")                      # email is case-insensitive
    assert ac.get("/api/auth/me").get_json()["user"]["id"] == uid


def test_passwords_are_hashed_never_stored_plain(ac, db_url):
    ac.register("a@example.com")
    with connect(db_url) as c:
        h = c.execute("SELECT password_hash FROM users").fetchone()["password_hash"]
    assert PW not in h and h.startswith(("scrypt:", "pbkdf2:"))


@pytest.mark.parametrize("email,pw,code", [
    ("not-an-email", PW, "invalid_email"),
    ("a@example.com", "short", "weak_password"),
    ("a@example.com", "password123", "weak_password"),
    ("alice@example.com", "alice-password1", "weak_password"),   # contains the email name prefix at the start
])
def test_registration_validation(ac, email, pw, code):
    r = ac.post("/api/auth/register", json={"email": email, "password": pw})
    assert r.status_code == 400 and r.get_json()["error"] == code


def test_duplicate_email_rejected(ac):
    ac.register("a@example.com")
    r = make_client(ac.c.application.config["DB_URL"]).post("/api/auth/register", json={"email": "A@example.com", "password": PW})
    assert r.status_code == 409


def test_wrong_password_and_unknown_user_look_identical(ac):
    ac.register("a@example.com")
    ac.logout()
    r1 = ac.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-password-1"})
    r2 = ac.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    assert r1.status_code == r2.status_code == 401 and r1.get_json() == r2.get_json()


def test_login_rate_limited_per_account(ac):
    ac.register("a@example.com")
    ac.logout()
    codes = [ac.post("/api/auth/login", json={"email": "a@example.com", "password": "bad-password-x"}).status_code
             for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8:] == [429, 429]
    # even the right password is refused while limited
    assert ac.post("/api/auth/login", json={"email": "a@example.com", "password": PW}).status_code == 429


def test_csrf_required_on_unsafe_methods(db_url):
    app = create_app(TestConfig)
    c = app.test_client()
    assert c.post("/api/auth/register", json={"email": "a@example.com", "password": PW}).status_code == 403
    tok = c.get("/api/auth/csrf").get_json()["csrf_token"]
    assert c.post("/api/auth/register", json={"email": "a@example.com", "password": PW},
                  headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert c.post("/api/auth/register", json={"email": "a@example.com", "password": PW},
                  headers={"X-CSRF-Token": tok}).status_code == 201


def test_session_is_rotated_on_login(ac):
    ac.register("a@example.com")
    before = ac.token
    ac.logout()
    ac.login("a@example.com")
    assert ac.token != before


def test_session_cookie_flags(db_url):
    class Prod(TestConfig):
        ENV, SECRET_KEY = "production", "s"
    c = create_app(Prod).test_client()
    r = c.get("/api/auth/csrf")
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Secure" in cookie


def test_production_refuses_to_start_without_secret_key(db_url):
    class Prod(TestConfig):
        ENV, SECRET_KEY = "production", None
    with pytest.raises(RuntimeError):
        create_app(Prod)


def test_delete_account_removes_user_data(ac, db_url):
    uid = ac.register("a@example.com")
    with connect(db_url) as c:
        c.execute("INSERT INTO profiles (user_id, data) VALUES (%s, '{}')", (uid,))
        c.execute("INSERT INTO applications (user_id, job_title) VALUES (%s, 'x')", (uid,))
        c.commit()
    assert ac.delete("/api/auth/account").status_code == 200
    with connect(db_url) as c:
        for t in ("users", "profiles", "applications"):
            assert c.execute(f"SELECT count(*) n FROM {t}").fetchone()["n"] == 0
    assert ac.get("/api/auth/me").get_json()["user"] is None


def test_audit_never_stores_secrets(db_url):
    accounts.audit(db_url, None, "x", detail={"password": "hunter2", "ok": 1})
    with connect(db_url) as c:
        d = c.execute("SELECT detail FROM audit_log").fetchone()["detail"]
    assert d == {"ok": 1}

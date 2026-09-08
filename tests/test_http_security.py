from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import fakeredis.aioredis
import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core import rate_limit
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_document_upload_token,
    decode_access_token,
    decode_document_upload_token,
    hash_password,
)
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.domain.models import (
    Company,
    CompanyRole,
    Document,
    DocumentPage,
    Project,
    ProjectMember,
    ProjectRole,
    User,
)


@compiles(JSONB, "sqlite")
def jsonb_for_sqlite(_type, _compiler, **_kw):
    return "JSON"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis = fakeredis.aioredis.FakeRedis()
    monkeypatch.setattr(rate_limit, "rate_limit_store", lambda: redis)
    monkeypatch.setattr(get_settings(), "document_storage_path", tmp_path)
    application = create_app()

    async def database():
        async with sessions() as session:
            yield session

    application.dependency_overrides[get_db_session] = database
    async with sessions() as session:
        companies = [Company(name="Company A"), Company(name="Company B")]
        session.add_all(companies)
        await session.flush()
        users = [
            User(
                company_id=companies[i % 2].id,
                email=f"user{i}@example.com",
                full_name=f"User {i}",
                password_hash=hash_password("a-test-password-123"),
                company_role=CompanyRole.OWNER,
            )
            for i in range(3)
        ]
        projects = [Project(company_id=c.id, name=c.name, code="TEST") for c in companies]
        session.add_all([*users, *projects])
        await session.flush()
        session.add_all(
            [
                ProjectMember(
                    project_id=projects[i % 2].id,
                    user_id=u.id,
                    role=ProjectRole.OWNER if i < 2 else ProjectRole.VIEWER,
                )
                for i, u in enumerate(users)
            ]
        )
        docs = [
            Document(
                project_id=p.id,
                name="drawing.pdf",
                storage_key=f"{p.id}/doc.pdf",
                sha256="a" * 64,
                mime_type="application/pdf",
            )
            for p in projects
        ]
        session.add_all(docs)
        await session.flush()
        session.add_all(
            [DocumentPage(project_id=d.project_id, document_id=d.id, page_number=1) for d in docs]
        )
        await session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="https://api.test"
    ) as http:
        yield http, users, projects, docs, redis
    await redis.aclose()
    await engine.dispose()


def authorization(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_real_http_tenant_and_role_isolation(client):
    http, users, projects, docs, _ = client
    own = f"/api/v1/projects/{projects[0].id}"
    foreign = f"/api/v1/projects/{projects[1].id}"
    assert (await http.get("/api/v1/projects")).status_code == 401
    listed = await http.get("/api/v1/projects", headers=authorization(users[0]))
    assert [p["id"] for p in listed.json()] == [str(projects[0].id)]
    for suffix in ["", "/structures", "/documents", "/calculations", "/members"]:
        response = await http.get(foreign + suffix, headers=authorization(users[0]))
        assert response.status_code == 404, (suffix, response.text)
    response = await http.get(
        f"{own}/documents/{docs[1].id}/download", headers=authorization(users[0])
    )
    assert response.status_code == 404
    response = await http.post(
        f"{own}/structures",
        headers=authorization(users[2]),
        json={"name": "No permission", "structure_type": "wall"},
    )
    assert response.status_code == 403
    assert "no-store" in listed.headers["cache-control"]
    assert listed.headers["x-content-type-options"] == "nosniff"


async def test_calculation_validates_source_ownership_and_finite_values(client):
    http, users, projects, docs, _ = client
    route = f"/api/v1/projects/{projects[0].id}/calculations"
    body = {
        "title": "Volume",
        "calculation_type": "concrete_pour",
        "input_data": {"length_m": 10, "height_m": 3, "thickness_m": 0.3},
        "sources": [{"document_id": str(docs[1].id), "page": 1}],
    }
    response = await http.post(route, json=body, headers=authorization(users[0]))
    assert response.status_code == 404
    body["sources"] = [{"document_id": str(docs[0].id), "page": 99}]
    assert (await http.post(route, json=body, headers=authorization(users[0]))).status_code == 422
    body["sources"][0]["page"] = 1
    valid = await http.post(route, json=body, headers=authorization(users[0]))
    assert valid.status_code == 201, valid.text
    assert valid.json()["result"]["gross_volume_m3"] == 9
    body["input_data"]["rebar_mass_kg"] = "Infinity"
    invalid = await http.post(route, json=body, headers=authorization(users[0]))
    assert invalid.status_code == 422, invalid.text


async def test_login_and_shared_rate_limit(client):
    http, _, _, _, redis = client
    response = await http.post(
        "/api/v1/auth/token",
        data={"username": "user0@example.com", "password": "a-test-password-123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert (
        await http.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 200
    for _ in range(12):
        response = await http.post(
            "/api/v1/auth/token", data={"username": "missing@example.com", "password": "wrong"}
        )
        assert response.status_code == 401
    response = await http.post(
        "/api/v1/auth/token", data={"username": "missing@example.com", "password": "wrong"}
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "300"
    keys = await redis.keys("cos:limit:login-email:*")
    assert all(b"example.com" not in key for key in keys)
    assert all([await redis.ttl(key) > 0 for key in keys])


async def test_upload_rejects_anonymous_wrong_project_and_fake_pdf(client):
    http, users, projects, _, _ = client
    path = f"/api/v1/projects/{projects[0].id}/documents"
    fake = {"file": ("attack.pdf", b"<html><script>alert(1)</script>", "application/pdf")}
    assert (await http.post(path, files=fake)).status_code == 401
    assert (await http.post(path, files=fake, headers=authorization(users[0]))).status_code == 422
    token = create_document_upload_token(users[0].id, projects[1].id)
    response = await http.post(
        path + "/direct-upload", files=fake, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    data = BytesIO()
    writer.write(data)
    response = await http.post(
        path,
        files={"file": ("../../drawing.pdf", data.getvalue(), "application/pdf")},
        headers=authorization(users[0]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["page_count"] == 1
    assert response.json()["name"] == "drawing.pdf"
    download = await http.get(
        path + f"/{response.json()['id']}/download", headers=authorization(users[0])
    )
    assert download.content.startswith(b"%PDF-")
    assert "attachment" in download.headers["content-disposition"]


async def test_body_limit_and_cors(client):
    http, users, projects, _, _ = client
    response = await http.post(
        "/api/v1/projects", content=b"x" * (1024 * 1024 + 1), headers=authorization(users[0])
    )
    assert response.status_code == 413
    for origin, allowed in [
        ("https://buildos.top", True),
        ("https://www.buildos.top", True),
        ("https://evil.example", False),
    ]:
        response = await http.options(
            f"/api/v1/projects/{projects[0].id}/documents/direct-upload",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        assert (response.headers.get("access-control-allow-origin") == origin) is allowed


def test_tokens_require_expiration_and_correct_purpose():
    settings = get_settings()
    user, project = uuid4(), uuid4()
    for kind in ["access", "document_upload"]:
        payload = {"sub": str(user), "type": kind, "project_id": str(project)}
        for expires in [None, datetime.now(UTC) - timedelta(seconds=5)]:
            if expires:
                payload["exp"] = expires
            token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
            with pytest.raises(jwt.InvalidTokenError):
                if kind == "access":
                    decode_access_token(token)
                else:
                    decode_document_upload_token(token, project)
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(create_document_upload_token(user, project))


async def test_limiter_fails_closed_on_redis_outage(monkeypatch):
    class BrokenStore:
        async def eval(self, *_args):
            raise RedisConnectionError("offline")

    monkeypatch.setattr(rate_limit, "rate_limit_store", lambda: BrokenStore())
    with pytest.raises(HTTPException) as error:
        await rate_limit.enforce_rate_limit("login", "test", 1, 60)
    assert error.value.status_code == 503


def test_public_deployments_do_not_expose_schema(monkeypatch):
    monkeypatch.setattr(get_settings(), "environment", "production")
    app = create_app()
    assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None


async def test_project_delete_requires_owner_confirmation_and_cascades(client):
    http, users, projects, docs, _ = client
    path = f"/api/v1/projects/{projects[0].id}"
    body = {"confirmation_code": "TEST"}
    assert (await http.request("DELETE", path, json=body)).status_code == 401
    assert (
        await http.request("DELETE", path, json=body, headers=authorization(users[1]))
    ).status_code == 404
    assert (
        await http.request("DELETE", path, json=body, headers=authorization(users[2]))
    ).status_code == 403
    assert (
        await http.request(
            "DELETE", path, json={"confirmation_code": "WRONG"}, headers=authorization(users[0])
        )
    ).status_code == 422
    assert (await http.get(path, headers=authorization(users[0]))).status_code == 200
    assert (
        await http.request("DELETE", path, json=body, headers=authorization(users[0]))
    ).status_code == 204
    assert (await http.get(path, headers=authorization(users[0]))).status_code == 404
    assert (await http.get(path + "/documents", headers=authorization(users[0]))).status_code == 404
    assert (
        await http.get(f"/api/v1/projects/{projects[1].id}", headers=authorization(users[1]))
    ).status_code == 200


async def test_document_deletion_is_scoped_and_confirmed(client):
    http, users, projects, docs, _ = client
    base = f"/api/v1/projects/{projects[0].id}"
    route = f"{base}/documents/{docs[0].id}"
    for actor, code in [(None, 401), (users[1], 404), (users[2], 403)]:
        headers = authorization(actor) if actor else {}
        result = await http.request("DELETE", route, headers=headers, json={"confirm": True})
        assert result.status_code == code
    result = await http.request(
        "DELETE", route, headers=authorization(users[0]), json={"confirm": False}
    )
    assert result.status_code == 422
    result = await http.request(
        "DELETE", route, headers=authorization(users[0]), json={"confirm": True}
    )
    assert result.status_code == 204
    assert (await http.get(route + "/download", headers=authorization(users[0]))).status_code == 404
    assert (await http.get(base, headers=authorization(users[0]))).status_code == 200
    foreign = await http.get(
        f"/api/v1/projects/{projects[1].id}/documents", headers=authorization(users[1])
    )
    assert len(foreign.json()) == 1

from collections.abc import Generator
import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import get_artic_client
from app.db import Base, get_db
from main import app


class FakeArtInstituteClient:
    def __init__(self, valid_ids: dict[int, str] | None = None):
        self.valid_ids = valid_ids or {}

    def place_exists(self, external_id: int) -> tuple[bool, str | None]:
        title = self.valid_ids.get(external_id)
        return (title is not None, title)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    fake_client = FakeArtInstituteClient(
        valid_ids={
            111: "Artwork 111",
            222: "Artwork 222",
            333: "Artwork 333",
            444: "Artwork 444",
            555: "Artwork 555",
            666: "Artwork 666",
            777: "Artwork 777",
            888: "Artwork 888",
            999: "Artwork 999",
            1000: "Artwork 1000",
            1001: "Artwork 1001",
            1002: "Artwork 1002",
        }
    )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_artic_client] = lambda: fake_client

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    token = base64.b64encode(b"admin:admin").decode("ascii")
    return {"Authorization": f"Basic {token}"}

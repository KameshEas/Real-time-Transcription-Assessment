import pytest
from fastapi.testclient import TestClient

from hinglish.bootstrap.app import create_app
from hinglish.bootstrap.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", use_fake_recognizer=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as c:
        yield c

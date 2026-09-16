import pytest
from django_celery_beat.schedulers import DatabaseScheduler

from polarrouteserver.celery import app

@pytest.fixture(scope="session")
def celery_config():
    return {"broker_url": "memory://", "result_backend": "cache+memory://"}

@pytest.fixture(scope="session")
def celery_includes():
    return ["polarrouteserver.route_api.tasks"]   # modules containing tasks

@pytest.fixture
def make_scheduler(db):
    created = []

    def _make():
        s = DatabaseScheduler(app=app)
        created.append(s)
        return s

    yield _make

    for s in created:
        s.sync()  # flush while the test DB still exists
        finalize = getattr(s, "_finalize", None)
        if finalize is not None:
            finalize.cancel()  # stop the exit-time sync from firing later
            
import os

import aiomoto
import pytest

@pytest.fixture(scope="function")
def s3_mock():
    """Starts moto S3 mock before each test and stops it after."""
    with aiomoto.mock_aws(server_mode=True):
        yield

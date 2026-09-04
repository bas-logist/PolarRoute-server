import os

import aiomoto
import pytest

# @pytest.fixture(scope="function")
# def s3_credentials(monkeypatch):
#     """Mocked S3 Credentials for moto."""

#     monkeypatch.setenv("POLARROUTE_S3_ENDPOINT_URL", "testing")
#     monkeypatch.setenv("POLARROUTE_S3_BUCKET", "testing")
#     monkeypatch.setenv("POLARROUTE_S3_KEY", "testing")
#     monkeypatch.setenv("POLARROUTE_S3_SECRET", "testing")


@pytest.fixture(scope="function")
def s3_mock():
    """Starts moto S3 mock before each test and stops it after."""
    with aiomoto.mock_aws(server_mode=True):
        yield

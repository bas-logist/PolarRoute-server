import os

import aiomoto
import pytest

@pytest.fixture(scope="function")
def s3_mock():
    """Starts moto S3 mock before each test and stops it after."""
    with aiomoto.mock_aws(server_mode=True):
        yield

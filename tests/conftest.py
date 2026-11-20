import pytest

from helpers import DATA_DIR


@pytest.fixture
def data_dir():
    return DATA_DIR

import pytest


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip = pytest.mark.skip(reason="pass --integration to run")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)

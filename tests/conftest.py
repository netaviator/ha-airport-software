"""Shared test fixtures."""
import sys
from pathlib import Path

import aiohttp.connector
import pytest
from aiohttp.resolver import ThreadedResolver

pytest_plugins = "pytest_homeassistant_custom_component"

# aiodns/pycares (aiohttp's default async DNS resolver when aiodns is
# installed) spawns a background "shutdown" thread on ClientSession
# teardown that outlives pytest-homeassistant-custom-component's strict
# thread-leak check (it isn't tied to the event loop's default executor,
# so `shutdown_default_executor()` doesn't wait for it). Tests never hit
# real DNS anyway (aioresponses intercepts everything), so force the
# plain threaded resolver, whose worker threads *are* tracked by the
# loop's default executor and get cleaned up in time.
aiohttp.connector.DefaultResolver = ThreadedResolver

# Add the repo root to sys.path so custom_components can be imported
REPO_ROOT = Path(__file__).parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_configure(config):
    """Configure pytest and ensure sys.path includes the repo root."""
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components importable in every test."""
    yield

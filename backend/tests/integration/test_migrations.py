import os
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings

pytestmark = pytest.mark.integration


def test_campaign_migration_upgrade_downgrade_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if not urlparse(database_url).path.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must target a database whose name ends with '_test'")

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(database_url)

    try:
        command.downgrade(config, "base")
        assert "campaigns" not in inspect(engine).get_table_names()

        command.upgrade(config, "head")
        inspector = inspect(engine)
        assert "campaigns" in inspector.get_table_names()
        assert "campaign_drafts" in inspector.get_table_names()
        assert "agent_runs" in inspector.get_table_names()
        constraint_names = {
            constraint["name"] for constraint in inspector.get_check_constraints("campaigns")
        }
        assert "ck_campaigns_status" in constraint_names
        assert "ck_campaigns_date_range" in constraint_names

        command.downgrade(config, "base")
        assert "campaigns" not in inspect(engine).get_table_names()
        assert "campaign_drafts" not in inspect(engine).get_table_names()

        command.upgrade(config, "head")
        assert "campaigns" in inspect(engine).get_table_names()
        assert "campaign_drafts" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
        get_settings.cache_clear()

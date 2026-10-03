"""Upgrade a populated legacy encounter table without inventing signatures."""

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/emr_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.core.encounter_migrations import migrate_encounter_lifecycle


class EncounterMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_legacy_rows_and_is_repeatable(self):
        engine = create_engine("sqlite://", poolclass=StaticPool)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE encounters (id INTEGER PRIMARY KEY, status VARCHAR)"))
            conn.execute(text("INSERT INTO encounters (id, status) VALUES (7, 'Completed')"))
            migrate_encounter_lifecycle(conn)
            migrate_encounter_lifecycle(conn)
            columns = {column["name"] for column in inspect(conn).get_columns("encounters")}
            self.assertTrue({"version", "signed_at", "signed_by_id", "draft_orders"}.issubset(columns))
            self.assertTrue(inspect(conn).has_table("encounter_amendments"))
            row = conn.execute(text("SELECT status, version, signed_at, signed_by_id FROM encounters WHERE id = 7")).one()
            self.assertEqual(row.status, "Completed")
            self.assertEqual(row.version, 1)
            self.assertIsNone(row.signed_at)
            self.assertIsNone(row.signed_by_id)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()

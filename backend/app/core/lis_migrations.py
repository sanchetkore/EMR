"""Upgrade legacy single-LIS patient mapping uniqueness without losing rows."""
from sqlalchemy import MetaData, Table, UniqueConstraint, inspect, text
from sqlalchemy.schema import CreateTable, CreateIndex


def migrate_patient_identity_uniqueness(conn):
    name = "patient_external_identities"
    inspector = inspect(conn)
    constraints = [c for c in inspector.get_unique_constraints(name)
                   if c["column_names"] == ["patient_id"]]
    indexes = [i for i in inspector.get_indexes(name)
               if i.get("unique") and i["column_names"] == ["patient_id"]
               and not i.get("duplicates_constraint")]
    if not constraints and not indexes:
        return
    quote = conn.dialect.identifier_preparer.quote
    if conn.dialect.name == "sqlite":
        # SQLite cannot DROP UNIQUE constraints. Rebuild this mapping table,
        # preserving all columns, rows, other constraints and indexes.
        original = Table(name, MetaData(), autoload_with=conn)
        replacement = original.to_metadata(original.metadata, name=name + "_upgrade")
        for constraint in list(replacement.constraints):
            if isinstance(constraint, UniqueConstraint) and list(constraint.columns.keys()) == ["patient_id"]:
                replacement.constraints.remove(constraint)
        replacement.indexes.clear()
        conn.execute(CreateTable(replacement))
        columns = ", ".join(quote(c.name) for c in original.columns)
        conn.execute(text(f"INSERT INTO {quote(replacement.name)} ({columns}) SELECT {columns} FROM {quote(name)}"))
        conn.execute(text(f"DROP TABLE {quote(name)}"))
        conn.execute(text(f"ALTER TABLE {quote(replacement.name)} RENAME TO {quote(name)}"))
        for index in original.indexes:
            if index.unique and list(index.columns.keys()) == ["patient_id"]:
                continue
            conn.execute(CreateIndex(index))
    elif conn.dialect.name == "postgresql":
        for constraint in constraints:
            conn.execute(text(f"ALTER TABLE {quote(name)} DROP CONSTRAINT {quote(constraint['name'])}"))
        for index in indexes:
            conn.execute(text(f"DROP INDEX {quote(index['name'])}"))
    else:
        raise RuntimeError("Unsupported database for LIS identity uniqueness upgrade")

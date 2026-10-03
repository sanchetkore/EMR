"""Copy the configured database into a separate SQLite database for local testing."""
import os
from datetime import datetime
from pathlib import Path
import sys

from dotenv import dotenv_values
from sqlalchemy import MetaData, create_engine, inspect, select, text

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
config = dotenv_values(root / '.env')
destination = root / f'emr_local_snapshot_{datetime.now():%Y%m%d_%H%M%S}.db'
os.environ['DATABASE_URL'] = f'sqlite:///{destination.as_posix()}'
import app.models
from app.core.database import Base


def main():
    source = create_engine(config['DATABASE_URL'], connect_args={'connect_timeout': 15})
    target = create_engine(os.environ['DATABASE_URL'])
    Base.metadata.create_all(target)
    counts = {}
    with source.connect().execution_options(isolation_level='REPEATABLE READ') as incoming:
        transaction = incoming.begin()
        incoming.execute(text('SET TRANSACTION READ ONLY'))
        existing = set(inspect(incoming).get_table_names())
        metadata = MetaData()
        names = [table.name for table in Base.metadata.sorted_tables if table.name in existing and table.name != 'lis_connector']
        metadata.reflect(bind=incoming, only=names, resolve_fks=False)
        with target.begin() as outgoing:
            for table in Base.metadata.sorted_tables:
                if table.name not in names:
                    continue
                columns = set(table.columns.keys())
                records = []
                for row in incoming.execute(select(metadata.tables[table.name])).mappings():
                    record = {key: value for key, value in row.items() if key in columns}
                    if table.name == 'clinic_profile':
                        record['notification_settings'] = {}
                    records.append(record)
                if records:
                    outgoing.execute(table.insert(), records)
                counts[table.name] = len(records)
        transaction.rollback()
    source.dispose()
    target.dispose()
    print(f'Local snapshot: {destination.name}')
    print({key: counts.get(key, 0) for key in ['patients', 'encounters', 'appointments', 'users', 'user_tabs']})
    print('Source was read-only. LIS connection and messaging credentials are excluded.')


if __name__ == '__main__':
    main()

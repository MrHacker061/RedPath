from sqlalchemy import create_engine, inspect, text

from redpath.database import migrate_database


def test_legacy_findings_receive_traceable_evidence_ref(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE findings (id VARCHAR(36) PRIMARY KEY, scan_import_id VARCHAR(36) NOT NULL)"))
        connection.execute(text("INSERT INTO findings (id, scan_import_id) VALUES ('finding-1', 'scan-1')"))

    migrate_database(engine)

    assert "evidence_ref" in {column["name"] for column in inspect(engine).get_columns("findings")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT evidence_ref FROM findings WHERE id = 'finding-1'")).scalar_one() == "scan-1"
    engine.dispose()

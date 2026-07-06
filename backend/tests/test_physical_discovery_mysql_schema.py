from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.models.physical_discovery import PhysicalDiscoveryDetail


def test_discovery_detail_instance_fk_uses_bigint_for_mysql():
    ddl = str(CreateTable(PhysicalDiscoveryDetail.__table__).compile(dialect=mysql.dialect()))

    assert "instance_id BIGINT" in ddl

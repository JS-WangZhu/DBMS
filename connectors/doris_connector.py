"""Doris database connector.

Apache Doris exposes a MySQL-compatible interface, so this connector
re-uses MySQLConnector with Doris-specific defaults and helpers.
"""

from typing import Any

from connectors.mysql_connector import MySQLConnector


class DorisConnector(MySQLConnector):
    """Connector for Apache Doris (MySQL-wire-compatible)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9030,
        user: str = "root",
        password: str = "",
        database: str = "",
        charset: str = "utf8mb4",
    ) -> None:
        super().__init__(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
        )

    # ------------------------------------------------------------------
    # Doris-specific helpers
    # ------------------------------------------------------------------

    def list_catalogs(self) -> list[str]:
        """Return the list of catalogs available in Doris."""
        rows = self.execute("SHOW CATALOGS")
        return [row.get("CatalogName", list(row.values())[0]) for row in rows]

    def list_backends(self) -> list[dict[str, Any]]:
        """Return the list of BE (Backend) nodes in the Doris cluster."""
        return self.execute("SHOW BACKENDS")

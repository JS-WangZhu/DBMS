"""MySQL database connector."""

from typing import Any

import pymysql
import pymysql.cursors

from connectors.base import BaseConnector


class MySQLConnector(BaseConnector):
    """Connector for MySQL databases using pymysql."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "",
        charset: str = "utf8mb4",
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.charset = charset
        self._connection: pymysql.connections.Connection | None = None

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open a connection to MySQL.

        Returns:
            True on success, False on failure.
        """
        try:
            self._connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database or None,
                charset=self.charset,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
            )
            return True
        except Exception:
            self._connection = None
            return False

    def disconnect(self) -> None:
        """Close the MySQL connection."""
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None

    def test_connection(self) -> bool:
        """Ping the server to verify the connection is alive."""
        if self._connection is None:
            return False
        try:
            self._connection.ping(reconnect=True)
            return True
        except Exception:
            return False

    def execute(self, command: str, *args: Any, **kwargs: Any) -> list[dict]:
        """Execute a SQL statement and return all result rows.

        Args:
            command: SQL statement to execute.
            *args: Positional parameters for the statement.
            **kwargs: Unused; reserved for API compatibility.

        Returns:
            A list of row dictionaries. Empty list for non-SELECT statements.

        Raises:
            RuntimeError: If no active connection exists.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to MySQL. Call connect() first.")
        with self._connection.cursor() as cursor:
            cursor.execute(command, args if args else None)
            self._connection.commit()
            try:
                return cursor.fetchall() or []
            except Exception:
                return []

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    # ------------------------------------------------------------------
    # MySQL-specific helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Identifier safety
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_identifier(name: str) -> str:
        """Return *name* with backticks escaped for use in SQL identifiers.

        Backticks inside the identifier are doubled per MySQL quoting rules.
        Any NUL bytes are rejected as they cannot appear in valid identifiers.
        """
        if "\x00" in name:
            raise ValueError(f"Invalid identifier (contains NUL byte): {name!r}")
        return name.replace("`", "``")

    def list_databases(self) -> list[str]:
        """Return a list of all database names on the server."""
        rows = self.execute("SHOW DATABASES")
        return [row["Database"] for row in rows]

    def list_tables(self, database: str | None = None) -> list[str]:
        """Return a list of table names in the given (or current) database."""
        if database:
            safe_db = self._safe_identifier(database)
            self.execute(f"USE `{safe_db}`")
        rows = self.execute("SHOW TABLES")
        if not rows:
            return []
        key = list(rows[0].keys())[0]
        return [row[key] for row in rows]

    def describe_table(self, table: str) -> list[dict]:
        """Return the column definitions for *table*."""
        safe_table = self._safe_identifier(table)
        return self.execute(f"DESCRIBE `{safe_table}`")

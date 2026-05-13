"""MongoDB connector."""

from typing import Any

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

from connectors.base import BaseConnector


class MongoDBConnector(BaseConnector):
    """Connector for MongoDB using pymongo."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 27017,
        user: str = "",
        password: str = "",
        auth_source: str = "admin",
        database: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.auth_source = auth_source
        self.database = database
        self._client: MongoClient | None = None

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Open a connection to MongoDB.

        Returns:
            True on success, False on failure.
        """
        try:
            kwargs: dict[str, Any] = {
                "host": self.host,
                "port": self.port,
                "serverSelectionTimeoutMS": 10_000,
            }
            if self.user:
                kwargs["username"] = self.user
                kwargs["password"] = self.password
                kwargs["authSource"] = self.auth_source
            self._client = MongoClient(**kwargs)
            # Force a round-trip to confirm the connection works.
            self._client.admin.command("ping")
            return True
        except (ConnectionFailure, OperationFailure):
            self._client = None
            return False
        except Exception:
            self._client = None
            return False

    def disconnect(self) -> None:
        """Close the MongoDB client."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def test_connection(self) -> bool:
        """Ping the MongoDB server."""
        if self._client is None:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    def execute(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Run a MongoDB command via ``db.command()``.

        The *command* string is passed directly to the current database's
        ``command()`` method, which accepts command names such as
        ``"listCollections"``, ``"dbStats"``, etc.

        Args:
            command: MongoDB command name or document.
            *args: Unused; reserved for API compatibility.
            **kwargs: Extra keyword arguments forwarded to ``db.command()``.

        Returns:
            The command result document.

        Raises:
            RuntimeError: If no active connection exists.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to MongoDB. Call connect() first.")
        db = self._get_db()
        return db.command(command, **kwargs)

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_db(self, database: str | None = None):
        """Return a pymongo Database object for the given (or default) name."""
        name = database or self.database or "admin"
        return self._client[name]

    # ------------------------------------------------------------------
    # MongoDB-specific helpers
    # ------------------------------------------------------------------

    def list_databases(self) -> list[str]:
        """Return a list of all database names on the server."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MongoDB.")
        return [db["name"] for db in self._client.list_databases()]

    def list_collections(self, database: str | None = None) -> list[str]:
        """Return a list of collection names in *database*."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MongoDB.")
        return self._get_db(database).list_collection_names()

    def find(
        self,
        collection: str,
        query: dict | None = None,
        database: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return up to *limit* documents from *collection* matching *query*.

        Args:
            collection: Collection name.
            query: MongoDB filter document (default: ``{}`` — all documents).
            database: Override the default database.
            limit: Maximum number of documents to return.

        Returns:
            A list of document dictionaries (``_id`` cast to str).
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to MongoDB.")
        col = self._get_db(database)[collection]
        docs = col.find(query or {}).limit(limit)
        results = []
        for doc in docs:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    def insert_one(
        self,
        collection: str,
        document: dict,
        database: str | None = None,
    ) -> str:
        """Insert a single document and return its inserted ``_id`` as str."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MongoDB.")
        col = self._get_db(database)[collection]
        result = col.insert_one(document)
        return str(result.inserted_id)

    def count_documents(
        self,
        collection: str,
        query: dict | None = None,
        database: str | None = None,
    ) -> int:
        """Return the number of documents in *collection* matching *query*."""
        if not self.is_connected:
            raise RuntimeError("Not connected to MongoDB.")
        col = self._get_db(database)[collection]
        return col.count_documents(query or {})

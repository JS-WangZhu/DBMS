"""Unit tests for the database connectors.

These tests use mocks / fakes so they run without a live database server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# MySQLConnector
# ---------------------------------------------------------------------------


class TestMySQLConnector:
    """Tests for MySQLConnector."""

    _PATCH = "connectors.mysql_connector.pymysql.connect"

    def _make_connector(self, **kwargs):
        from connectors.mysql_connector import MySQLConnector
        defaults = dict(host="127.0.0.1", port=3306, user="root", password="", database="test")
        defaults.update(kwargs)
        return MySQLConnector(**defaults)

    def test_initial_state(self):
        conn = self._make_connector()
        assert not conn.is_connected

    def test_connect_success(self):
        conn = self._make_connector()
        mock_connection = MagicMock()
        with patch(self._PATCH, return_value=mock_connection):
            result = conn.connect()
        assert result is True
        assert conn.is_connected

    def test_connect_failure(self):
        conn = self._make_connector()
        with patch(self._PATCH, side_effect=Exception("refused")):
            result = conn.connect()
        assert result is False
        assert not conn.is_connected

    def test_disconnect(self):
        conn = self._make_connector()
        mock_connection = MagicMock()
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        conn.disconnect()
        assert not conn.is_connected
        mock_connection.close.assert_called_once()

    def test_test_connection_when_connected(self):
        conn = self._make_connector()
        mock_connection = MagicMock()
        mock_connection.ping.return_value = None  # pymysql ping returns None on success
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        assert conn.test_connection() is True

    def test_test_connection_when_disconnected(self):
        conn = self._make_connector()
        assert conn.test_connection() is False

    def test_execute_raises_when_disconnected(self):
        conn = self._make_connector()
        with pytest.raises(RuntimeError, match="Not connected"):
            conn.execute("SELECT 1")

    def test_execute_returns_rows(self):
        conn = self._make_connector()
        expected = [{"1": 1}]
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = expected
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        result = conn.execute("SELECT 1")
        assert result == expected

    def test_list_databases(self):
        conn = self._make_connector()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {"Database": "information_schema"},
            {"Database": "test"},
        ]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        databases = conn.list_databases()
        assert databases == ["information_schema", "test"]

    def test_list_tables(self):
        conn = self._make_connector()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [{"Tables_in_test": "users"}]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        tables = conn.list_tables()
        assert tables == ["users"]

    def test_safe_identifier_escapes_backticks(self):
        from connectors.mysql_connector import MySQLConnector
        assert MySQLConnector._safe_identifier("normal_name") == "normal_name"
        assert MySQLConnector._safe_identifier("name`with`ticks") == "name``with``ticks"

    def test_safe_identifier_rejects_nul(self):
        from connectors.mysql_connector import MySQLConnector
        with pytest.raises(ValueError, match="NUL"):
            MySQLConnector._safe_identifier("bad\x00name")

    def test_describe_table(self):
        conn = self._make_connector()
        expected = [{"Field": "id", "Type": "int(11)", "Null": "NO", "Key": "PRI", "Default": None, "Extra": ""}]
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = expected
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        result = conn.describe_table("users")
        assert result == expected


# ---------------------------------------------------------------------------
# DorisConnector
# ---------------------------------------------------------------------------


class TestDorisConnector:
    """Tests for DorisConnector."""

    _PATCH = "connectors.mysql_connector.pymysql.connect"

    def _make_connector(self, **kwargs):
        from connectors.doris_connector import DorisConnector
        defaults = dict(host="127.0.0.1", port=9030, user="root", password="", database="")
        defaults.update(kwargs)
        return DorisConnector(**defaults)

    def test_default_port(self):
        conn = self._make_connector()
        assert conn.port == 9030

    def test_inherits_mysql_connector(self):
        from connectors.mysql_connector import MySQLConnector
        from connectors.doris_connector import DorisConnector
        conn = self._make_connector()
        assert isinstance(conn, MySQLConnector)

    def test_connect_success(self):
        conn = self._make_connector()
        mock_connection = MagicMock()
        with patch(self._PATCH, return_value=mock_connection):
            result = conn.connect()
        assert result is True
        assert conn.is_connected

    def test_list_catalogs(self):
        conn = self._make_connector()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [{"CatalogName": "internal"}, {"CatalogName": "hive"}]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        catalogs = conn.list_catalogs()
        assert catalogs == ["internal", "hive"]

    def test_list_backends(self):
        conn = self._make_connector()
        backend_row = {"BackendId": "1", "Host": "doris-be", "Port": "9050"}
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [backend_row]
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        with patch(self._PATCH, return_value=mock_connection):
            conn.connect()
        backends = conn.list_backends()
        assert backends == [backend_row]


# ---------------------------------------------------------------------------
# RedisConnector
# ---------------------------------------------------------------------------


class TestRedisConnector:
    """Tests for RedisConnector."""

    _PATCH = "connectors.redis_connector.redis_lib.Redis"

    def _make_connector(self, **kwargs):
        from connectors.redis_connector import RedisConnector
        defaults = dict(host="127.0.0.1", port=6379, password="", db=0)
        defaults.update(kwargs)
        return RedisConnector(**defaults)

    def test_initial_state(self):
        conn = self._make_connector()
        assert not conn.is_connected

    def test_connect_success(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch(self._PATCH, return_value=mock_client):
            result = conn.connect()
        assert result is True
        assert conn.is_connected

    def test_connect_failure(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("refused")
        with patch(self._PATCH, return_value=mock_client):
            result = conn.connect()
        assert result is False
        assert not conn.is_connected

    def test_disconnect(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        conn.disconnect()
        assert not conn.is_connected
        mock_client.close.assert_called_once()

    def test_test_connection_when_connected(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        assert conn.test_connection() is True

    def test_test_connection_when_disconnected(self):
        conn = self._make_connector()
        assert conn.test_connection() is False

    def test_execute_raises_when_disconnected(self):
        conn = self._make_connector()
        with pytest.raises(RuntimeError, match="Not connected"):
            conn.execute("PING")

    def test_execute_ping(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.execute_command.return_value = "PONG"
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        result = conn.execute("PING")
        assert result == "PONG"
        mock_client.execute_command.assert_called_with("PING")

    def test_execute_set_command(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.execute_command.return_value = "OK"
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        result = conn.execute("SET mykey myvalue")
        assert result == "OK"
        mock_client.execute_command.assert_called_with("SET", "mykey", "myvalue")

    def test_list_keys(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.scan.return_value = (0, ["key1", "key2"])
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        keys = conn.list_keys("*")
        assert set(keys) == {"key1", "key2"}

    def test_get_db_size(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.dbsize.return_value = 42
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        assert conn.get_db_size() == 42

    def test_get_key_type(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.type.return_value = "string"
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        assert conn.get_key_type("mykey") == "string"

    def test_get_key_value_string(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.type.return_value = "string"
        mock_client.get.return_value = "hello"
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        assert conn.get_key_value("mykey") == "hello"

    def test_get_key_value_hash(self):
        conn = self._make_connector()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.type.return_value = "hash"
        mock_client.hgetall.return_value = {"field1": "val1"}
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        assert conn.get_key_value("mykey") == {"field1": "val1"}


# ---------------------------------------------------------------------------
# MongoDBConnector
# ---------------------------------------------------------------------------


class TestMongoDBConnector:
    """Tests for MongoDBConnector."""

    _PATCH = "connectors.mongodb_connector.MongoClient"

    def _make_connector(self, **kwargs):
        from connectors.mongodb_connector import MongoDBConnector
        defaults = dict(host="127.0.0.1", port=27017, user="", password="", database="test")
        defaults.update(kwargs)
        return MongoDBConnector(**defaults)

    def _mock_client(self):
        """Return a MagicMock that looks like a healthy MongoClient."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}
        return mock_client

    def test_initial_state(self):
        conn = self._make_connector()
        assert not conn.is_connected

    def test_connect_success(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        with patch(self._PATCH, return_value=mock_client):
            result = conn.connect()
        assert result is True
        assert conn.is_connected

    def test_connect_failure(self):
        conn = self._make_connector()
        from pymongo.errors import ConnectionFailure
        with patch(self._PATCH, side_effect=ConnectionFailure("refused")):
            result = conn.connect()
        assert result is False
        assert not conn.is_connected

    def test_disconnect(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        conn.disconnect()
        assert not conn.is_connected
        mock_client.close.assert_called_once()

    def test_test_connection_when_connected(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        assert conn.test_connection() is True

    def test_test_connection_when_disconnected(self):
        conn = self._make_connector()
        assert conn.test_connection() is False

    def test_execute_raises_when_disconnected(self):
        conn = self._make_connector()
        with pytest.raises(RuntimeError, match="Not connected"):
            conn.execute("dbStats")

    def test_list_databases(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        mock_client.list_databases.return_value = [
            {"name": "admin", "sizeOnDisk": 1},
            {"name": "test", "sizeOnDisk": 2},
        ]
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        databases = conn.list_databases()
        assert databases == ["admin", "test"]

    def test_list_collections(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["users", "orders"]
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        collections = conn.list_collections("test")
        assert collections == ["users", "orders"]

    def test_find(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        from bson import ObjectId
        raw_docs = [{"_id": ObjectId("507f1f77bcf86cd799439011"), "name": "Alice"}]
        mock_col = MagicMock()
        mock_col.find.return_value.limit.return_value = iter(raw_docs)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        conn._get_db = MagicMock(return_value=mock_db)
        docs = conn.find("users", query={}, database="test", limit=10)
        assert len(docs) == 1
        assert docs[0]["name"] == "Alice"
        assert docs[0]["_id"] == "507f1f77bcf86cd799439011"

    def test_insert_one(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        mock_col = MagicMock()
        from bson import ObjectId
        inserted_id = ObjectId("507f1f77bcf86cd799439011")
        mock_col.insert_one.return_value.inserted_id = inserted_id
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        conn._get_db = MagicMock(return_value=mock_db)
        result = conn.insert_one("users", {"name": "Bob"})
        assert result == "507f1f77bcf86cd799439011"

    def test_count_documents(self):
        conn = self._make_connector()
        mock_client = self._mock_client()
        mock_col = MagicMock()
        mock_col.count_documents.return_value = 5
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        with patch(self._PATCH, return_value=mock_client):
            conn.connect()
        conn._get_db = MagicMock(return_value=mock_db)
        assert conn.count_documents("users") == 5

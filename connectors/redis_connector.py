"""Redis connector."""

from typing import Any

import redis as redis_lib

from connectors.base import BaseConnector


class RedisConnector(BaseConnector):
    """Connector for Redis using the redis-py client."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        password: str = "",
        db: int = 0,
        decode_responses: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password or None
        self.db = db
        self.decode_responses = decode_responses
        self._client: redis_lib.Redis | None = None

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Create a Redis client and verify connectivity with PING.

        Returns:
            True on success, False on failure.
        """
        try:
            self._client = redis_lib.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
                decode_responses=self.decode_responses,
                socket_connect_timeout=10,
            )
            self._client.ping()
            return True
        except Exception:
            self._client = None
            return False

    def disconnect(self) -> None:
        """Close all connections in the connection pool."""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    def test_connection(self) -> bool:
        """Send PING to verify the connection is alive."""
        if self._client is None:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def execute(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a raw Redis command string.

        The first token is treated as the command name; the remaining
        tokens are its arguments.

        Args:
            command: Full Redis command string, e.g. ``"SET foo bar"``.
            *args: Unused; reserved for API compatibility.
            **kwargs: Unused; reserved for API compatibility.

        Returns:
            The raw reply from the Redis server.

        Raises:
            RuntimeError: If no active connection exists.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to Redis. Call connect() first.")
        parts = command.split()
        if not parts:
            return None
        cmd_name, cmd_args = parts[0].upper(), parts[1:]
        return self._client.execute_command(cmd_name, *cmd_args)

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Redis-specific helpers
    # ------------------------------------------------------------------

    def get_info(self, section: str = "all") -> dict[str, Any]:
        """Return Redis server INFO as a dictionary."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Redis.")
        return self._client.info(section)

    def list_keys(self, pattern: str = "*") -> list[str]:
        """Return keys matching *pattern* (uses SCAN for safety)."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Redis.")
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = self._client.scan(cursor=cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    def get_key_type(self, key: str) -> str:
        """Return the Redis type of *key*."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Redis.")
        return self._client.type(key)

    def get_key_value(self, key: str) -> Any:
        """Return the value of *key* in a type-aware manner."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Redis.")
        key_type = self.get_key_type(key)
        if key_type == "string":
            return self._client.get(key)
        if key_type == "list":
            return self._client.lrange(key, 0, -1)
        if key_type == "set":
            return list(self._client.smembers(key))
        if key_type == "zset":
            return self._client.zrange(key, 0, -1, withscores=True)
        if key_type == "hash":
            return self._client.hgetall(key)
        return None

    def get_db_size(self) -> int:
        """Return the number of keys in the currently selected database."""
        if not self.is_connected:
            raise RuntimeError("Not connected to Redis.")
        return self._client.dbsize()

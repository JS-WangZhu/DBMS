"""Base connector interface for all database connectors."""

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Abstract base class that all database connectors must implement."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish a connection to the database.

        Returns:
            True if the connection was successful, False otherwise.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the database connection."""

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify that the current connection is alive.

        Returns:
            True if the connection is alive, False otherwise.
        """

    @abstractmethod
    def execute(self, command: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a command or query against the database.

        Args:
            command: The query or command string to execute.
            *args: Positional arguments passed to the underlying driver.
            **kwargs: Keyword arguments passed to the underlying driver.

        Returns:
            The result of the command/query.
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if an active connection exists."""

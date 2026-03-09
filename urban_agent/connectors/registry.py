"""
Connector registry for discoverable external system access.
"""

from __future__ import annotations

from typing import Dict, Optional

from .base import BaseConnector


class ConnectorRegistry:
    def __init__(self):
        self._connectors: Dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.name] = connector

    def get(self, name: str) -> Optional[BaseConnector]:
        return self._connectors.get(name)

    def list_connectors(self) -> Dict[str, str]:
        return {
            name: connector.__class__.__name__
            for name, connector in self._connectors.items()
        }

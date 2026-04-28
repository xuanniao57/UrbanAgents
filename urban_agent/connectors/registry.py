"""
Connector registry for discoverable external system access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseConnector


@dataclass
class ConnectorSpec:
    """Machine-readable connector declaration for runtime discovery."""

    name: str
    connector_class: str
    protocol: str = "urban-agent-open-spec/v1"
    capabilities: List[str] = field(default_factory=list)
    input_modalities: List[str] = field(default_factory=list)
    output_modalities: List[str] = field(default_factory=list)
    human_review_surfaces: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "connector_class": self.connector_class,
            "protocol": self.protocol,
            "capabilities": list(self.capabilities),
            "input_modalities": list(self.input_modalities),
            "output_modalities": list(self.output_modalities),
            "human_review_surfaces": list(self.human_review_surfaces),
            "metadata": dict(self.metadata),
        }


class ConnectorRegistry:
    def __init__(self):
        self._connectors: Dict[str, BaseConnector] = {}
        self._specs: Dict[str, ConnectorSpec] = {}

    def register(
        self,
        connector: BaseConnector,
        *,
        protocol: str = "urban-agent-open-spec/v1",
        capabilities: Optional[List[str]] = None,
        input_modalities: Optional[List[str]] = None,
        output_modalities: Optional[List[str]] = None,
        human_review_surfaces: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._connectors[connector.name] = connector
        self._specs[connector.name] = ConnectorSpec(
            name=connector.name,
            connector_class=connector.__class__.__name__,
            protocol=protocol,
            capabilities=capabilities or [],
            input_modalities=input_modalities or [],
            output_modalities=output_modalities or [],
            human_review_surfaces=human_review_surfaces or [],
            metadata=metadata or {},
        )

    def get(self, name: str) -> Optional[BaseConnector]:
        return self._connectors.get(name)

    def describe(self, name: str) -> Optional[Dict[str, Any]]:
        spec = self._specs.get(name)
        return spec.to_dict() if spec else None

    def list_connectors(self) -> Dict[str, str]:
        return {
            name: connector.__class__.__name__
            for name, connector in self._connectors.items()
        }

    def list_specs(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: spec.to_dict()
            for name, spec in self._specs.items()
        }

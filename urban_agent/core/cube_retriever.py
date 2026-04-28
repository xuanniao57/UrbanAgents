"""CubeGraph-inspired experimental retriever for spatio-temporal memory."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


CellId = Tuple[int, int]


@dataclass
class _Candidate:
    score: float
    layer: Optional[int]
    source: str
    distance: int


class CubeGraphMemoryBackend:
    """Hierarchical cube retrieval for experimental memory augmentation.

    This is not a reimplementation of CubeGraph's ANN index. It ports the parts
    that are structurally useful for UrbanAgent's memory layer: hierarchical
    spatial partitioning, filter-size-aware layer selection, and adjacent-cell
    expansion for retrieval.
    """

    DEFAULT_LAYER_STEPS = (1.0, 0.25, 0.05)

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        raw_steps = self.config.get("layer_steps", self.DEFAULT_LAYER_STEPS)
        self.layer_steps = tuple(float(step) for step in raw_steps)
        self.max_neighbors = int(self.config.get("max_neighbors", 1))
        self.max_results = int(self.config.get("max_results", 5))
        self.layer_weight_decay = float(self.config.get("layer_weight_decay", 0.12))

        self.entries: Dict[str, Dict[str, Any]] = {}
        self.spatial_cells: Dict[int, Dict[CellId, Set[str]]] = {
            layer: {} for layer in range(len(self.layer_steps))
        }
        self.location_entries: Dict[str, Set[str]] = {}

    def index_entry(self, entry: Dict[str, Any]) -> str:
        payload = entry.get("experience", entry)
        entry_id = str(uuid.uuid4())
        self.entries[entry_id] = entry

        for token in self._extract_location_tokens(payload):
            self.location_entries.setdefault(token, set()).add(entry_id)

        for layer, step in enumerate(self.layer_steps):
            layer_map = self.spatial_cells[layer]
            for spatial_ref in self._extract_spatial_refs(payload):
                for cell in self._cells_for_ref(spatial_ref, step):
                    layer_map.setdefault(cell, set()).add(entry_id)

        return entry_id

    def search(
        self,
        query: Dict[str, Any],
        query_tc: Optional[Any] = None,
        task_type: str = "",
    ) -> List[Dict[str, Any]]:
        candidates: Dict[str, _Candidate] = {}
        spatial_refs = self._extract_spatial_refs(query)
        location_tokens = self._extract_location_tokens(query)

        primary_layer = self._select_primary_layer(spatial_refs)
        active_layers = self._active_layers(primary_layer) if spatial_refs else []

        for token in location_tokens:
            for entry_id in self.location_entries.get(token, set()):
                self._accumulate(candidates, entry_id, 0.7, None, "location", 0)

        for layer in active_layers:
            layer_weight = max(0.2, 1.0 - layer * self.layer_weight_decay)
            layer_map = self.spatial_cells[layer]
            step = self.layer_steps[layer]
            for spatial_ref in spatial_refs:
                for cell, distance in self._query_cells(spatial_ref, step):
                    for entry_id in layer_map.get(cell, set()):
                        spatial_score = max(0.2, 1.0 - 0.25 * distance)
                        self._accumulate(
                            candidates,
                            entry_id,
                            layer_weight * spatial_score,
                            layer,
                            "spatial",
                            distance,
                        )

        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for entry_id, candidate in candidates.items():
            entry = dict(self.entries[entry_id])
            score = candidate.score
            score += self._task_bonus(entry, task_type)
            score += self._temporal_bonus(entry, query_tc)
            entry["cube_match"] = {
                "score": round(score, 4),
                "source": candidate.source,
                "layer": candidate.layer,
                "distance": candidate.distance,
            }
            ranked.append((score, entry))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in ranked[: self.max_results]]

    def get_stats(self) -> Dict[str, Any]:
        occupied_cells = sum(len(cells) for cells in self.spatial_cells.values())
        return {
            "entries": len(self.entries),
            "occupied_cells": occupied_cells,
            "location_buckets": len(self.location_entries),
            "layers": len(self.layer_steps),
        }

    def _accumulate(
        self,
        candidates: Dict[str, _Candidate],
        entry_id: str,
        score: float,
        layer: Optional[int],
        source: str,
        distance: int,
    ) -> None:
        current = candidates.get(entry_id)
        if current is None or score > current.score:
            candidates[entry_id] = _Candidate(
                score=score,
                layer=layer,
                source=source,
                distance=distance,
            )

    def _select_primary_layer(self, spatial_refs: List[Dict[str, float]]) -> int:
        if not spatial_refs:
            return len(self.layer_steps) - 1
        extent = max(self._ref_extent(spatial_ref) for spatial_ref in spatial_refs)
        for layer, step in enumerate(self.layer_steps):
            if extent >= step:
                return layer
        return len(self.layer_steps) - 1

    def _active_layers(self, primary_layer: int) -> List[int]:
        start = max(0, primary_layer - 1)
        end = min(len(self.layer_steps), primary_layer + 2)
        return list(range(start, end))

    def _task_bonus(self, entry: Dict[str, Any], task_type: str) -> float:
        if not task_type:
            return 0.0
        entry_task_type = self._extract_task_type(entry.get("experience", entry))
        return 0.2 if entry_task_type == task_type else 0.0

    def _temporal_bonus(self, entry: Dict[str, Any], query_tc: Optional[Any]) -> float:
        if not isinstance(query_tc, dict):
            return 0.0
        entry_tc = entry.get("temporal_context")
        if not isinstance(entry_tc, dict):
            return 0.0

        bonus = 0.0
        if entry_tc.get("period") == query_tc.get("period"):
            bonus += 0.15
        if entry_tc.get("is_weekend") == query_tc.get("is_weekend"):
            bonus += 0.1
        if entry_tc.get("season") == query_tc.get("season"):
            bonus += 0.05
        return bonus

    def _extract_spatial_refs(self, payload: Any) -> List[Dict[str, float]]:
        refs: List[Dict[str, float]] = []
        self._collect_spatial_refs(payload, refs)
        return refs

    def _collect_spatial_refs(self, value: Any, refs: List[Dict[str, float]]) -> None:
        if isinstance(value, dict):
            if self._is_bounds_dict(value):
                refs.append({
                    "min_lon": float(value["min_lon"]),
                    "min_lat": float(value["min_lat"]),
                    "max_lon": float(value["max_lon"]),
                    "max_lat": float(value["max_lat"]),
                })
            elif {"lon", "lat"}.issubset(value.keys()):
                lon = float(value["lon"])
                lat = float(value["lat"])
                refs.append({
                    "min_lon": lon,
                    "min_lat": lat,
                    "max_lon": lon,
                    "max_lat": lat,
                })
            elif {"longitude", "latitude"}.issubset(value.keys()):
                lon = float(value["longitude"])
                lat = float(value["latitude"])
                refs.append({
                    "min_lon": lon,
                    "min_lat": lat,
                    "max_lon": lon,
                    "max_lat": lat,
                })

            centroid = value.get("centroid")
            if isinstance(centroid, (list, tuple)) and len(centroid) >= 2:
                lon = float(centroid[0])
                lat = float(centroid[1])
                refs.append({
                    "min_lon": lon,
                    "min_lat": lat,
                    "max_lon": lon,
                    "max_lat": lat,
                })

            coordinates = value.get("coordinates")
            if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
                first = coordinates[0]
                second = coordinates[1]
                if isinstance(first, (int, float)) and isinstance(second, (int, float)):
                    lon = float(first)
                    lat = float(second)
                    refs.append({
                        "min_lon": lon,
                        "min_lat": lat,
                        "max_lon": lon,
                        "max_lat": lat,
                    })

            for nested in value.values():
                self._collect_spatial_refs(nested, refs)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                self._collect_spatial_refs(nested, refs)

    def _extract_location_tokens(self, payload: Any) -> List[str]:
        tokens: Set[str] = set()
        self._collect_location_tokens(payload, tokens)
        return sorted(tokens)

    def _collect_location_tokens(self, value: Any, tokens: Set[str]) -> None:
        if isinstance(value, dict):
            for key in ("location", "city", "district_name", "start", "end"):
                item = value.get(key)
                if isinstance(item, str) and item.strip():
                    tokens.add(item.strip().lower())
            for nested in value.values():
                self._collect_location_tokens(nested, tokens)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                self._collect_location_tokens(nested, tokens)

    def _extract_task_type(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        if isinstance(payload.get("task_type"), str):
            return payload["task_type"]
        task = payload.get("task")
        if isinstance(task, dict) and isinstance(task.get("task_type"), str):
            return task["task_type"]
        return ""

    def _cells_for_ref(self, spatial_ref: Dict[str, float], step: float) -> List[CellId]:
        min_x = math.floor(spatial_ref["min_lon"] / step)
        max_x = math.floor(spatial_ref["max_lon"] / step)
        min_y = math.floor(spatial_ref["min_lat"] / step)
        max_y = math.floor(spatial_ref["max_lat"] / step)

        cells: List[CellId] = []
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                cells.append((cell_x, cell_y))
        return cells

    def _query_cells(self, spatial_ref: Dict[str, float], step: float) -> List[Tuple[CellId, int]]:
        base_cells = self._cells_for_ref(spatial_ref, step)
        if not base_cells:
            return []

        candidates: List[Tuple[CellId, int]] = []
        seen: Set[CellId] = set()
        for cell in base_cells:
            for delta_x in range(-self.max_neighbors, self.max_neighbors + 1):
                for delta_y in range(-self.max_neighbors, self.max_neighbors + 1):
                    neighbor = (cell[0] + delta_x, cell[1] + delta_y)
                    if neighbor in seen:
                        continue
                    seen.add(neighbor)
                    distance = abs(delta_x) + abs(delta_y)
                    candidates.append((neighbor, distance))
        candidates.sort(key=lambda item: item[1])
        return candidates

    def _ref_extent(self, spatial_ref: Dict[str, float]) -> float:
        width = max(0.0, spatial_ref["max_lon"] - spatial_ref["min_lon"])
        height = max(0.0, spatial_ref["max_lat"] - spatial_ref["min_lat"])
        return max(width, height)

    def _is_bounds_dict(self, value: Dict[str, Any]) -> bool:
        return {"min_lon", "min_lat", "max_lon", "max_lat"}.issubset(value.keys())


def normalize_temporal_context(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return {
            "period": value.get("period"),
            "is_weekend": value.get("is_weekend"),
            "season": value.get("season"),
            "timestamp": value.get("timestamp"),
        }

    timestamp = getattr(value, "timestamp", None)
    if isinstance(timestamp, datetime):
        return {
            "period": getattr(value, "period", None),
            "is_weekend": getattr(value, "is_weekend", None),
            "season": getattr(value, "season", None),
            "timestamp": timestamp.isoformat(),
        }

    return None
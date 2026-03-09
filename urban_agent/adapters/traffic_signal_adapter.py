"""
Traffic signal adapter for bridging CityBench simulator states to UrbanAgent tasks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TrafficPhaseOption:
    option: str
    original_phase_index: Optional[int]
    lane_count: int
    vehicle_count: int
    waiting_vehicle_count: int
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "option": self.option,
            "original_phase_index": self.original_phase_index,
            "lane_count": self.lane_count,
            "vehicle_count": self.vehicle_count,
            "waiting_vehicle_count": self.waiting_vehicle_count,
            "description": self.description,
        }


class TrafficSignalAdapter:
    """
    Bridge layer between CityBench traffic signal runtime and UrbanAgent task input.

    It converts simulator-specific phase state into a small, stable task schema that
    the agent can reason over, and converts the agent's answer back into a phase index.
    """

    OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    def build_task_from_queue_lengths(
        self,
        city: str,
        queue_lengths: Dict[str, int],
        current_phase: Optional[str] = None,
    ) -> Dict[str, Any]:
        sorted_items = sorted(queue_lengths.items(), key=lambda item: item[0])
        phase_options: List[TrafficPhaseOption] = []
        phase_map: Dict[str, str] = {}

        for index, (phase_name, waiting_count) in enumerate(sorted_items):
            option = self.OPTION_LABELS[index]
            phase_map[option] = phase_name
            phase_options.append(
                TrafficPhaseOption(
                    option=option,
                    original_phase_index=None,
                    lane_count=1,
                    vehicle_count=int(waiting_count) + 2,
                    waiting_vehicle_count=int(waiting_count),
                    description=(
                        f"Option {option}: serve {phase_name}, "
                        f"waiting vehicles={int(waiting_count)}"
                    ),
                )
            )

        return {
            "task_type": "traffic_signal",
            "data_type": "text",
            "city": city,
            "question": f"Select the next green phase for {city}.",
            "current_phase": current_phase,
            "phase_map": phase_map,
            "phase_options": [option.to_dict() for option in phase_options],
            "queue_lengths": {key: int(value) for key, value in queue_lengths.items()},
        }

    def build_task_from_citybench_state(
        self,
        city: str,
        junction: Any,
        vehicle_counts: Any,
        waiting_counts: Any,
        current_phase_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        phase_options: List[TrafficPhaseOption] = []
        phase_map: Dict[str, int] = {}
        filtered_index = 0

        for original_index, phase in enumerate(junction.tl.phases):
            green_indices: List[int] = []
            valid_phase = True
            for lane_index, phase_state in enumerate(phase.states):
                if getattr(phase_state, "name", None) == "YELLOW":
                    valid_phase = False
                    break
                if getattr(phase_state, "name", None) == "GREEN":
                    green_indices.append(lane_index)

            if not valid_phase:
                continue

            lane_ids = set()
            total_vehicle_count = 0
            total_waiting_count = 0
            for green_index in green_indices:
                pre_lane_index = junction.lanes[green_index].predecessors[0].index
                lane_ids.add(pre_lane_index)
            for lane_id in lane_ids:
                total_vehicle_count += int(vehicle_counts[lane_id])
                total_waiting_count += int(waiting_counts[lane_id])

            option = self.OPTION_LABELS[filtered_index]
            phase_map[option] = original_index
            phase_options.append(
                TrafficPhaseOption(
                    option=option,
                    original_phase_index=original_index,
                    lane_count=len(lane_ids),
                    vehicle_count=total_vehicle_count,
                    waiting_vehicle_count=total_waiting_count,
                    description=(
                        f"Option {option}: phase {original_index}, lanes={len(lane_ids)}, "
                        f"vehicles={total_vehicle_count}, waiting={total_waiting_count}"
                    ),
                )
            )
            filtered_index += 1

        return {
            "task_type": "traffic_signal",
            "data_type": "text",
            "city": city,
            "question": "Select the next green phase for the intersection.",
            "current_phase_index": current_phase_index,
            "phase_map": phase_map,
            "phase_options": [option.to_dict() for option in phase_options],
        }

    def pick_default_option(self, task: Dict[str, Any]) -> Optional[str]:
        phase_options = task.get("phase_options", [])
        if not phase_options:
            return None
        best = max(
            phase_options,
            key=lambda item: (
                int(item.get("waiting_vehicle_count", 0)),
                int(item.get("vehicle_count", 0)),
            ),
        )
        return best.get("option")

    def parse_agent_choice(self, payload: Dict[str, Any]) -> Optional[str]:
        for key in ["selected_option", "phase_option", "answer", "final_answer"]:
            value = payload.get(key)
            if not value:
                continue
            if isinstance(value, str):
                signal_match = re.search(r"<signal>([A-Z]|\d+)</signal>", value, re.IGNORECASE)
                if signal_match:
                    return signal_match.group(1).upper()
                letter_match = re.search(r"\b([A-Z])\b", value.upper())
                if letter_match:
                    return letter_match.group(1)
        return None

    def resolve_phase_index(self, task: Dict[str, Any], selected_option: Optional[str]) -> Optional[int]:
        if not selected_option:
            return None
        phase_map = task.get("phase_map", {})
        return phase_map.get(selected_option)

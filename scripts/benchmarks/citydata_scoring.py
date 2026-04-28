from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from urban_agent.adapters import TrafficSignalAdapter


TRAFFIC_ADAPTER = TrafficSignalAdapter()
EVAL_ONLY_KEYS = {"ground_truth", "ground_truth_option", "ground_truth_destination"}
ACTION_KEYS = {
    "numerical_answer",
    "predicted_population",
    "objects",
    "detected_objects",
    "identified_city",
    "selected_option",
    "selected_phase",
    "predicted_location",
    "route_actions",
    "selected_destination",
    "signal_plan",
    "exploration_plan",
    "answer",
    "route",
}


def sanitize_task_for_inference(task: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(task, dict):
        return task
    return {key: value for key, value in task.items() if key not in EVAL_ONLY_KEYS}


def make_case_record(
    case_id: str,
    task_type: str,
    task: Dict[str, Any],
    ground_truth: Any = None,
    ground_truth_option: Any = None,
    ground_truth_destination: Any = None,
) -> Dict[str, Any]:
    raw_ground_truth = ground_truth if ground_truth is not None else task.get("ground_truth")
    option_ground_truth = ground_truth_option if ground_truth_option is not None else task.get("ground_truth_option")
    destination_ground_truth = (
        ground_truth_destination if ground_truth_destination is not None else task.get("ground_truth_destination")
    )

    return {
        "case_id": case_id,
        "task_type": task_type,
        "task": sanitize_task_for_inference(task),
        "ground_truth": option_ground_truth if option_ground_truth is not None else raw_ground_truth,
        "ground_truth_raw": raw_ground_truth,
        "ground_truth_option": option_ground_truth,
        "ground_truth_destination": destination_ground_truth,
    }


def evaluate_citydata_case(
    case: Dict[str, Any],
    output: Dict[str, Any],
    is_bare_model: bool = False,
) -> Tuple[Any, Dict[str, Any]]:
    task_type = case["task_type"]
    task = case["task"]
    action = _extract_action_payload(output)
    answer_text = _extract_answer_text(output, action)

    prediction: Any = answer_text
    detail: Dict[str, Any]

    if task_type == "population_prediction":
        selected_option = action.get("selected_option") or _extract_choice(answer_text, task.get("choices", {}))
        if selected_option and case.get("ground_truth_option"):
            prediction = str(selected_option).upper()
            detail = {
                "accuracy": 1.0 if prediction == str(case["ground_truth_option"]).upper() else 0.0,
                "predicted_option": prediction,
                "ground_truth_option": case.get("ground_truth_option"),
                "metric_type": "Option_Accuracy",
            }
        else:
            predicted_value = action.get("numerical_answer")
            if predicted_value is None:
                predicted_value = action.get("predicted_population")
            if predicted_value is None:
                predicted_value = _extract_first_number(answer_text)
            if predicted_value is None:
                prediction = ""
                detail = {"accuracy": 0.0, "error": "Invalid prediction"}
            else:
                ground_truth = case.get("ground_truth_raw")
                prediction = predicted_value
                relative_error = abs(float(predicted_value) - float(ground_truth)) / max(float(ground_truth), 1.0)
                detail = {
                    "accuracy": max(0.0, 1.0 - relative_error),
                    "predicted": float(predicted_value),
                    "ground_truth": ground_truth,
                    "relative_error": relative_error,
                    "metric_type": "Relative_Error",
                }
    elif task_type == "object_detection":
        prediction = action.get("objects") or action.get("detected_objects") or _extract_object_list(answer_text)
        detail = _object_detection_detail(prediction, case.get("ground_truth_raw") or [])
    elif task_type == "geolocation":
        prediction = action.get("identified_city") or _extract_city(answer_text, task.get("city_options", [])) or answer_text
        ground_truth = case.get("ground_truth_raw") or case.get("ground_truth")
        detail = {
            "accuracy": 1.0 if _normalize_text(prediction) == _normalize_text(ground_truth) else 0.0,
            "predicted": prediction,
            "ground_truth": ground_truth,
            "metric_type": "City_Accuracy",
        }
    elif task_type == "geoqa":
        predicted_option = action.get("selected_option") or _extract_choice(answer_text, task.get("choices", {}))
        prediction = predicted_option or answer_text
        detail = {
            "accuracy": 1.0 if predicted_option and str(predicted_option).upper() == str(case.get("ground_truth")).upper() else 0.0,
            "predicted": predicted_option,
            "ground_truth": case.get("ground_truth"),
            "metric_type": "Option_Accuracy",
        }
    elif task_type == "mobility_prediction":
        predicted_location = action.get("predicted_location")
        if predicted_location is None:
            predicted_location = _extract_first_number(answer_text)
            if predicted_location is None:
                predicted_location = answer_text
        prediction = predicted_location
        ground_truth = case.get("ground_truth_raw") or case.get("ground_truth")
        detail = {
            "accuracy": 1.0 if predicted_location == ground_truth else 0.0,
            "predicted": predicted_location,
            "ground_truth": ground_truth,
            "metric_type": "Acc@1",
        }
    elif task_type == "traffic_signal":
        predicted_option = action.get("selected_option")
        predicted_phase = action.get("selected_phase")
        if predicted_option is None:
            predicted_option = TRAFFIC_ADAPTER.parse_agent_choice({
                "selected_option": action.get("selected_option"),
                "answer": answer_text,
                "final_answer": output.get("final_answer", ""),
            })
        if case.get("ground_truth_option") is not None:
            prediction = predicted_option or predicted_phase or answer_text
            detail = {
                "accuracy": 1.0 if predicted_option and str(predicted_option).upper() == str(case["ground_truth_option"]).upper() else 0.0,
                "predicted_option": predicted_option,
                "ground_truth_option": case.get("ground_truth_option"),
                "predicted": predicted_phase,
                "ground_truth": case.get("ground_truth_raw"),
                "proxy": True,
                "metric_type": "Option_Accuracy",
            }
        else:
            prediction = predicted_phase or predicted_option or answer_text
            detail = {
                "accuracy": 1.0 if predicted_phase == case.get("ground_truth") else 0.0,
                "predicted": predicted_phase,
                "ground_truth": case.get("ground_truth"),
                "metric_type": "Phase_Accuracy",
            }
    elif task_type == "outdoor_navigation":
        prediction = action.get("route_actions") or _extract_route_actions(answer_text)
        ground_truth = case.get("ground_truth_raw") or case.get("ground_truth") or []
        detail = {
            "accuracy": 1.0 if prediction == ground_truth else 0.0,
            "predicted": prediction,
            "ground_truth": ground_truth,
            "metric_type": "Exact_Action_Match",
        }
    elif task_type == "urban_exploration":
        predicted_option = action.get("selected_option") or _extract_choice(answer_text)
        predicted_destination = action.get("selected_destination")
        if predicted_option is not None:
            prediction = predicted_option
            detail = {
                "accuracy": 1.0 if str(predicted_option).upper() == str(case.get("ground_truth")).upper() else 0.0,
                "predicted": predicted_option,
                "ground_truth": case.get("ground_truth"),
                "selected_destination": predicted_destination,
                "metric_type": "Option_Accuracy",
            }
        else:
            prediction = predicted_destination or answer_text
            detail = {
                "accuracy": 1.0 if predicted_destination and predicted_destination == case.get("ground_truth_destination") else 0.0,
                "predicted_destination": predicted_destination,
                "ground_truth_destination": case.get("ground_truth_destination"),
                "metric_type": "Destination_Accuracy",
            }
    else:
        prediction = output.get("final_answer", "")
        detail = {"accuracy": 0.0, "error": "Unsupported task type"}

    score = float(detail.get("accuracy", 0.0))
    eval_result = {
        "task_type": task_type,
        "is_bare_model": is_bare_model,
        "task_outcome": detail,
        "overall_score": score,
    }
    if is_bare_model:
        eval_result.update({
            "state_perception": {"status": "N/A", "note": "裸模型无感知模块"},
            "decision_sequence": {"status": "N/A", "note": "裸模型无决策序列"},
            "reasoning_depth": {"status": "N/A", "note": "裸模型无显式推理"},
            "tool_usage": {"status": "N/A", "note": "裸模型无工具使用"},
        })
    return prediction, eval_result


def prediction_to_log_string(prediction: Any) -> str:
    if isinstance(prediction, str):
        return prediction
    try:
        return json.dumps(prediction, ensure_ascii=False, default=str)
    except Exception:
        return str(prediction)


def build_safe_vanilla_prompt(task: Dict[str, Any], task_type: str) -> str:
    sections: List[str] = [
        "You are answering an urban analysis question.",
        f"Task type: {task_type}",
    ]

    question = task.get("question") or task.get("task_instruction")
    if question:
        sections.append(f"Question: {question}")

    if task_type == "population_prediction":
        indicator_values = task.get("indicator_values") or {}
        if indicator_values:
            sections.append("Indicators:\n" + _format_mapping(indicator_values))
        if task.get("choices"):
            sections.append("Options:\n" + _format_choices(task["choices"]))
    elif task_type == "object_detection":
        sections.append("This task depends on image content, but visual input is not provided in this direct-text baseline.")
        sections.append("If you cannot infer the answer from text alone, answer unknown.")
    elif task_type == "geolocation":
        city_options = task.get("city_options") or []
        if city_options:
            sections.append("Candidate cities: " + ", ".join(str(city) for city in city_options))
        sections.append("This task depends on street-view imagery, but visual input is not provided in this direct-text baseline.")
        sections.append("If you cannot infer the answer from text alone, answer unknown.")
    elif task_type == "geoqa":
        if task.get("choices"):
            sections.append("Options:\n" + _format_choices(task["choices"]))
    elif task_type == "mobility_prediction":
        if task.get("historical_data"):
            sections.append("Historical stays:\n" + _format_sequence(task["historical_data"]))
        if task.get("context_stay"):
            sections.append("Recent context stays:\n" + _format_sequence(task["context_stay"]))
        if task.get("target_stay"):
            sections.append(f"Predict target stay: {task['target_stay']}")
    elif task_type == "traffic_signal":
        if task.get("queue_lengths"):
            sections.append("Queue lengths:\n" + _format_mapping(task["queue_lengths"]))
        if task.get("phase_options"):
            sections.append("Phase options:\n" + _format_sequence(task["phase_options"]))
        if task.get("current_phase"):
            sections.append(f"Current phase: {task['current_phase']}")
    elif task_type == "outdoor_navigation":
        if task.get("start") or task.get("end"):
            sections.append(f"Start: {task.get('start', 'unknown')} | End: {task.get('end', 'unknown')}")
        if task.get("steps"):
            sections.append("Navigation observations:\n" + _format_sequence(task["steps"]))
    elif task_type == "urban_exploration":
        if task.get("candidates"):
            sections.append("Candidates:\n" + _format_sequence(task["candidates"]))
    else:
        safe_keys = ["question", "task_instruction", "choices", "indicator_values", "historical_data", "context_stay", "target_stay", "queue_lengths", "steps", "candidates"]
        safe_task = {key: task[key] for key in safe_keys if key in task}
        if safe_task:
            sections.append("Context:\n" + json.dumps(safe_task, ensure_ascii=False, default=str))

    sections.append("Answer directly and concisely.")
    sections.append("For multiple-choice questions, return only the option letter when possible.")
    return "\n".join(section for section in sections if section)


def _extract_action_payload(output: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(output.get("action"), dict):
        candidates.append(output["action"])

    results = output.get("results", {})
    if isinstance(results, dict):
        subtask_results = results.get("subtask_results", {})
        if isinstance(subtask_results, dict):
            for subtask in subtask_results.values():
                result = subtask.get("result")
                if isinstance(result, dict):
                    if isinstance(result.get("action"), dict):
                        candidates.append(result["action"])
                    candidates.append(result)

    for candidate in reversed(candidates):
        normalized = _normalize_action_payload(candidate)
        if any(key in normalized for key in ACTION_KEYS):
            return normalized
    return _normalize_action_payload(candidates[-1]) if candidates else {}


def _normalize_action_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    signal_plan = normalized.get("signal_plan")
    if isinstance(signal_plan, dict):
        for key, value in signal_plan.items():
            normalized.setdefault(key, value)
    exploration_plan = normalized.get("exploration_plan")
    if isinstance(exploration_plan, dict):
        for key, value in exploration_plan.items():
            normalized.setdefault(key, value)
    return normalized


def _extract_answer_text(output: Dict[str, Any], action: Dict[str, Any]) -> str:
    for candidate in [
        output.get("final_answer"),
        action.get("answer"),
        action.get("route"),
        action.get("report"),
    ]:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _extract_choice(text: str, choices: Optional[Dict[str, Any]] = None) -> Optional[str]:
    if not isinstance(text, str) or not text.strip():
        return None
    upper_text = text.upper().strip()
    if re.fullmatch(r"[A-E]", upper_text):
        return upper_text
    direct_match = re.search(r"\b([A-E])\b", upper_text)
    if direct_match:
        return direct_match.group(1)
    if choices:
        lower_text = text.strip().lower()
        for key, value in choices.items():
            value_text = str(value).strip().lower()
            if value_text and value_text in lower_text:
                return str(key).upper()
    return None


def _extract_first_number(text: str) -> Optional[float]:
    if not isinstance(text, str) or not text.strip():
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    value = float(match.group(0))
    return int(value) if value.is_integer() else value


def _extract_object_list(text: str) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    raw = text.split(":", 1)[-1]
    objects = []
    for item in raw.split(","):
        cleaned = item.strip().strip(".[]()")
        if cleaned:
            objects.append(cleaned.lower())
    return objects


def _object_detection_detail(predicted_objects: List[Any], ground_truth: List[Any]) -> Dict[str, Any]:
    predicted = {str(item).lower().strip() for item in predicted_objects if str(item).strip()}
    truth = {str(item).lower().strip() for item in ground_truth if str(item).strip()}
    if not predicted:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1_score": 0.0,
            "detected_count": 0,
            "metric_type": "F1",
        }
    precision = len(predicted & truth) / len(predicted) if predicted else 0.0
    recall = len(predicted & truth) / len(truth) if truth else 0.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "accuracy": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "detected_count": len(predicted),
        "metric_type": "F1",
    }


def _extract_city(text: str, city_options: List[str]) -> Optional[str]:
    if not isinstance(text, str) or not text.strip():
        return None
    lower_text = text.lower()
    for city in city_options:
        if city.lower() in lower_text:
            return city
    return None


def _extract_route_actions(text: str) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    lower_text = text.lower()
    actions: List[str] = []
    for pattern, label in [
        ("turn left", "turn_left"),
        ("turn right", "turn_right"),
        ("go straight", "go_straight"),
        ("head straight", "go_straight"),
        ("forward", "forward"),
        ("stop", "stop"),
    ]:
        if pattern in lower_text:
            actions.append(label)
    return actions


def _normalize_text(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _format_choices(choices: Dict[str, Any]) -> str:
    return "\n".join(f"  {key}: {value}" for key, value in choices.items())


def _format_mapping(mapping: Dict[str, Any]) -> str:
    return "\n".join(f"  {key}: {value}" for key, value in mapping.items())


def _format_sequence(values: List[Any]) -> str:
    lines = []
    for value in values:
        if isinstance(value, dict):
            lines.append(f"  - {json.dumps(value, ensure_ascii=False, default=str)}")
        else:
            lines.append(f"  - {value}")
    return "\n".join(lines)
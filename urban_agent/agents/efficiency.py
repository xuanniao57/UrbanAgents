"""
Efficiency Tracker — 逐层 token/latency/cost 追踪

产出 GeoAgent Table 4 等价的效率数据:
- 每 agent 每 task 的 token 消耗 (input + output)
- 每 agent 每 task 的延迟 (秒)
- 每 agent 每 task 的成本 (基于模型定价)

Usage:
    tracker = EfficiencyTracker()
    with tracker.track("planner"):
        result = await planner.execute(msg)
    report = tracker.summarize()
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional


# ---------------------------------------------------------------------------
# Default pricing (USD per 1K tokens, 2024 pricing)
# ---------------------------------------------------------------------------
MODEL_PRICING = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "deepseek-v3": {"input": 0.00014, "output": 0.00028},
    "qwen-2.5-72b": {"input": 0.0009, "output": 0.0009},
    "default": {"input": 0.005, "output": 0.015},
}


@dataclass
class StepRecord:
    """Single tracking record for one agent invocation."""
    layer: str           # "planner", "analyst", "perception", ...
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "default"
    task_type: str = ""
    success: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        pricing = MODEL_PRICING.get(self.model, MODEL_PRICING["default"])
        return (self.input_tokens * pricing["input"] + self.output_tokens * pricing["output"]) / 1000


class EfficiencyTracker:
    """
    Per-layer efficiency tracker.

    Integrates with MultiAgentOrchestrator to collect latency, token,
    and cost data for each agent invocation.
    """

    def __init__(self, model: str = "default") -> None:
        self.model = model
        self._records: List[StepRecord] = []
        self._active_start: Optional[float] = None
        self._active_label: Optional[str] = None

    # ------------------------------------------------------------------
    # Context-manager API (preferred)
    # ------------------------------------------------------------------

    @contextmanager
    def track(self, layer: str, task_type: str = "") -> Generator[StepRecord, None, None]:
        """
        Context manager for tracking a single agent step.

        Usage:
            with tracker.track("planner") as rec:
                result = await planner.execute(msg)
                rec.input_tokens = count_tokens(msg)
                rec.output_tokens = count_tokens(result)
        """
        rec = StepRecord(layer=layer, model=self.model, task_type=task_type)
        start = time.perf_counter()
        try:
            yield rec
        except Exception:
            rec.success = False
            raise
        finally:
            rec.latency_s = round(time.perf_counter() - start, 4)
            self._records.append(rec)

    # ------------------------------------------------------------------
    # Manual API (fallback)
    # ------------------------------------------------------------------

    def start(self, layer: str) -> None:
        self._active_label = layer
        self._active_start = time.perf_counter()

    def stop(self, input_tokens: int = 0, output_tokens: int = 0, success: bool = True) -> StepRecord:
        elapsed = time.perf_counter() - (self._active_start or time.perf_counter())
        rec = StepRecord(
            layer=self._active_label or "unknown",
            latency_s=round(elapsed, 4),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model,
            success=success,
        )
        self._records.append(rec)
        self._active_label = None
        self._active_start = None
        return rec

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @property
    def records(self) -> List[StepRecord]:
        return list(self._records)

    def summarize(self) -> Dict[str, Any]:
        """
        Aggregate into per-layer summary (GeoAgent Table 4 format).

        Returns:
            {
                "per_layer": {
                    "planner": {"count": 5, "avg_latency_s": 1.2, ...},
                    ...
                },
                "total": {"total_tokens": 12345, "total_cost_usd": 0.12, ...}
            }
        """
        from collections import defaultdict

        by_layer: Dict[str, List[StepRecord]] = defaultdict(list)
        for rec in self._records:
            by_layer[rec.layer].append(rec)

        per_layer = {}
        total_tokens = 0
        total_cost = 0.0
        total_latency = 0.0

        for layer, recs in sorted(by_layer.items()):
            count = len(recs)
            tokens = sum(r.total_tokens for r in recs)
            cost = sum(r.cost_usd for r in recs)
            latency = sum(r.latency_s for r in recs)
            per_layer[layer] = {
                "count": count,
                "total_tokens": tokens,
                "avg_tokens": round(tokens / count, 1) if count else 0,
                "total_cost_usd": round(cost, 6),
                "avg_latency_s": round(latency / count, 4) if count else 0,
                "success_rate": round(sum(1 for r in recs if r.success) / count, 4) if count else 0,
            }
            total_tokens += tokens
            total_cost += cost
            total_latency += latency

        return {
            "per_layer": per_layer,
            "total": {
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 6),
                "total_latency_s": round(total_latency, 4),
                "num_steps": len(self._records),
            },
        }

    def to_table_rows(self) -> List[Dict[str, Any]]:
        """Export as flat table (for paper Table 4)."""
        summary = self.summarize()
        rows = []
        for layer, stats in summary["per_layer"].items():
            rows.append({"Agent/Layer": layer, **stats})
        rows.append({"Agent/Layer": "TOTAL", **summary["total"]})
        return rows

    def reset(self) -> None:
        self._records.clear()

"""
Memory Module
时空记忆管理模块 (v3 — Temporal Enhancement)

新增组件:
- TemporalContext: 结构化时间元数据
- ACT-R activation: 时空激活度模型 (替换 token overlap)
- Multi-granularity temporal matching (替换 stub _time_match)
- MemoryReflector: LLM 驱动反思压缩 (时间维度分组)
- TemporalPatternDetector: 纯统计的周期模式检测

所有新组件可通过 ablation flags 独立开关。
"""

import json
import logging
import math
import re
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field

try:
    from experimental.cube_retriever import CubeGraphMemoryBackend, normalize_temporal_context
except Exception:  # pragma: no cover - optional experimental plugin
    CubeGraphMemoryBackend = None  # type: ignore[assignment]

    def normalize_temporal_context(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict"):
            return value.to_dict()
        return None

logger = logging.getLogger(__name__)


def _json_dump_safe(value: Any) -> str:
    return json.dumps(value, default=str)


def _tokenize_text(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", _json_dump_safe(value).lower()))


# ── TemporalContext (C1) ───────────────────────────────────────────

@dataclass
class TemporalContext:
    """结构化时间元数据，支持多粒度匹配。"""
    timestamp: datetime
    hour_of_day: int        # 0-23
    day_of_week: int        # 0=Mon, 6=Sun
    is_weekend: bool
    period: str             # morning_peak|daytime|evening_peak|night|early_morning
    season: str             # spring|summer|autumn|winter
    month: int              # 1-12
    week_of_year: int       # 1-53

    @classmethod
    def from_datetime(cls, dt: datetime) -> "TemporalContext":
        hour = dt.hour
        if 7 <= hour < 9:
            period = "morning_peak"
        elif 9 <= hour < 17:
            period = "daytime"
        elif 17 <= hour < 19:
            period = "evening_peak"
        elif 19 <= hour < 23:
            period = "night"
        else:
            period = "early_morning"

        month = dt.month
        if 3 <= month <= 5:
            season = "spring"
        elif 6 <= month <= 8:
            season = "summer"
        elif 9 <= month <= 11:
            season = "autumn"
        else:
            season = "winter"

        return cls(
            timestamp=dt,
            hour_of_day=hour,
            day_of_week=dt.weekday(),
            is_weekend=dt.weekday() >= 5,
            period=period,
            season=season,
            month=month,
            week_of_year=dt.isocalendar()[1],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
            "is_weekend": self.is_weekend,
            "period": self.period,
            "season": self.season,
            "month": self.month,
            "week_of_year": self.week_of_year,
        }


# ── Temporal matching helpers (C3) ─────────────────────────────────

_TASK_GRANULARITY: Dict[str, str] = {
    "mobility_prediction": "same_period",
    "traffic_signal": "same_period",
    "outdoor_navigation": "same_day_type",
    "urban_exploration": "same_season",
    "population_prediction": "any",
    "object_detection": "any",
    "geolocation": "any",
}

_GRANULARITY_SCORES: Dict[str, float] = {
    "exact_hour": 1.0,
    "same_period": 0.8,
    "same_day_type": 0.6,
    "same_week": 0.5,
    "same_month": 0.3,
    "same_season": 0.2,
    "any": 0.1,
}

_CATEGORY_DECAY: Dict[str, float] = {
    "observation": 0.05,
    "intervention": 0.02,
    "topological_graph": 0.005,
    "landmark": 0.001,
    "reflection": 0.005,
}

_CATEGORY_WEIGHT: Dict[str, float] = {
    "reflection": 1.2,
    "topological_graph": 1.0,
    "landmark": 1.2,
    "intervention": 0.8,
    "observation": 0.5,
}


def _tc_from_any(obj: Any) -> Optional[TemporalContext]:
    """Safely convert TemporalContext | dict | None → TemporalContext."""
    if isinstance(obj, TemporalContext):
        return obj
    if isinstance(obj, dict):
        try:
            ts = obj.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            elif not isinstance(ts, datetime):
                ts = datetime.now()
            return TemporalContext(
                timestamp=ts,
                hour_of_day=int(obj.get("hour_of_day", ts.hour)),
                day_of_week=int(obj.get("day_of_week", ts.weekday())),
                is_weekend=bool(obj.get("is_weekend", ts.weekday() >= 5)),
                period=str(obj.get("period", "daytime")),
                season=str(obj.get("season", "spring")),
                month=int(obj.get("month", ts.month)),
                week_of_year=int(obj.get("week_of_year", ts.isocalendar()[1])),
            )
        except Exception:
            return None
    return None


def temporal_match(
    memory_tc: Any,
    query_tc: Any,
    granularity: str = "same_period",
) -> float:
    """Additive multi-granularity temporal matching. Returns 0.0-1.0.

    Each matching dimension contributes independently, with a bonus for
    matching the task-relevant granularity.  This ensures two memories
    that share the same hour but differ on period/weekday/season receive
    different scores.
    """
    mtc = _tc_from_any(memory_tc)
    qtc = _tc_from_any(query_tc)
    if mtc is None or qtc is None:
        return 0.1

    # Additive weights (sum to ~1.0 when all match)
    score = 0.0
    if mtc.hour_of_day == qtc.hour_of_day:
        score += 0.15
    if mtc.period == qtc.period:
        score += 0.25
    if mtc.is_weekend == qtc.is_weekend:
        score += 0.20
    if mtc.week_of_year == qtc.week_of_year:
        score += 0.10
    if mtc.month == qtc.month:
        score += 0.10
    if mtc.season == qtc.season:
        score += 0.15

    # Bonus for matching at the task-relevant granularity
    _granularity_match = {
        "same_period": mtc.period == qtc.period,
        "same_day_type": mtc.is_weekend == qtc.is_weekend,
        "same_season": mtc.season == qtc.season,
    }
    if _granularity_match.get(granularity, False):
        score += 0.05

    return min(max(score, 0.05), 1.0)


# ── TemporalPatternDetector (C5) ──────────────────────────────────

@dataclass
class TemporalPattern:
    location: str
    task_type: str
    peak_periods: List[str]
    weekday_vs_weekend: Optional[str]   # weekday_heavier|weekend_heavier|similar
    seasonal_trend: Optional[str]
    monotonic_trend: Optional[str]      # improving|declining|stable
    sample_count: int
    confidence: float


class TemporalPatternDetector:
    """纯统计的周期性模式检测器。"""
    MIN_SAMPLES = 5

    def detect_patterns(
        self, memories: List[Dict], location: str, task_type: str,
    ) -> Optional[TemporalPattern]:
        if len(memories) < self.MIN_SAMPLES:
            return None

        period_counts: Dict[str, int] = {}
        day_type_counts = {"weekday": 0, "weekend": 0}
        season_counts: Dict[str, int] = {}
        scores_over_time: List[float] = []

        for mem in memories:
            tc = _tc_from_any(mem.get("temporal_context"))
            if tc is None:
                continue
            period_counts[tc.period] = period_counts.get(tc.period, 0) + 1
            if tc.is_weekend:
                day_type_counts["weekend"] += 1
            else:
                day_type_counts["weekday"] += 1
            season_counts[tc.season] = season_counts.get(tc.season, 0) + 1

            score = mem.get("importance")
            if isinstance(score, (int, float)):
                scores_over_time.append(float(score))

        total = sum(period_counts.values()) or 1
        peak_periods = [p for p, c in period_counts.items() if c / total > 0.3]

        wd, we = day_type_counts["weekday"], day_type_counts["weekend"]
        if wd + we > 0:
            ratio = wd / (wd + we)
            weekday_vs_weekend = (
                "weekday_heavier" if ratio > 0.7
                else "weekend_heavier" if ratio < 0.3
                else "similar"
            )
        else:
            weekday_vs_weekend = None

        seasonal_trend = None
        if season_counts:
            top_season = max(season_counts, key=lambda k: season_counts[k])
            if season_counts[top_season] / total > 0.4:
                seasonal_trend = f"{top_season}_peak"

        monotonic_trend: Optional[str] = "stable"
        if len(scores_over_time) >= 3:
            diffs = [scores_over_time[i + 1] - scores_over_time[i] for i in range(len(scores_over_time) - 1)]
            pos = sum(1 for d in diffs if d > 0)
            neg = sum(1 for d in diffs if d < 0)
            if pos / len(diffs) > 0.6:
                monotonic_trend = "improving"
            elif neg / len(diffs) > 0.6:
                monotonic_trend = "declining"

        return TemporalPattern(
            location=location,
            task_type=task_type,
            peak_periods=peak_periods,
            weekday_vs_weekend=weekday_vs_weekend,
            seasonal_trend=seasonal_trend,
            monotonic_trend=monotonic_trend,
            sample_count=len(memories),
            confidence=min(1.0, len(memories) / 20.0),
        )


# ── MemoryReflector (C4) ──────────────────────────────────────────

@dataclass
class ReflectionEntry:
    id: str
    summary: str
    spatial_patterns: List[str]
    temporal_patterns: List[str]
    reusable_insights: List[str]
    source_locations: List[str]
    source_task_types: List[str]
    source_periods: List[str]
    source_ids: List[str]
    importance: float
    temporal_context: Optional[Dict]
    timestamp: str


class MemoryReflector:
    """LLM 驱动的反思压缩 (时间维度增强分组)。"""
    CAPACITY_THRESHOLD = 0.8

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    async def should_reflect(self, short_term_memory: deque) -> bool:
        if short_term_memory.maxlen is None:
            return False
        return len(short_term_memory) >= int(short_term_memory.maxlen * self.CAPACITY_THRESHOLD)

    async def reflect(self, short_term_memory: deque) -> List[ReflectionEntry]:
        groups: Dict[tuple, List[Dict]] = {}
        for mem in short_term_memory:
            if not isinstance(mem, dict):
                continue
            locations = _extract_locations(mem)
            task_type = _extract_task_type_flat(mem)
            tc = _tc_from_any(mem.get("temporal_context"))
            period = tc.period if tc else "unknown"
            key = (tuple(locations) if locations else ("unknown",), task_type or "unknown", period)
            groups.setdefault(key, []).append(mem)

        reflections: List[ReflectionEntry] = []
        for (locs, task_type, period), group_mems in groups.items():
            if len(group_mems) < 2:
                continue
            ref = await self._reflect_group(list(locs), task_type, period, group_mems)
            if ref:
                reflections.append(ref)
        return reflections

    async def _reflect_group(
        self, locations: List[str], task_type: str, period: str, memories: List[Dict],
    ) -> Optional[ReflectionEntry]:
        if self.llm_client and len(memories) >= 3:
            mem_summaries = []
            for i, mem in enumerate(memories[:10]):
                task = mem.get("task", {})
                action = mem.get("action", {})
                bits = []
                if task.get("city"):
                    bits.append(f"city={task['city']}")
                if task.get("task_type"):
                    bits.append(f"type={task['task_type']}")
                answer = action.get("answer", action.get("predicted_location", ""))
                if answer:
                    bits.append(f"result={answer}")
                mem_summaries.append(f"  [{i + 1}] {', '.join(bits)}")

            prompt = (
                f"Summarize {len(memories)} analysis experiences for "
                f"location={locations}, task_type={task_type}, period={period}.\n"
                "Extract: key findings, spatial patterns, temporal patterns, reusable insights.\n\n"
                + "\n".join(mem_summaries)
                + '\n\nJSON: {"summary":str,"spatial_patterns":[str],"temporal_patterns":[str],"reusable_insights":[str]}'
            )
            try:
                response = await self.llm_client.generate(prompt)
                json_match = re.search(r"\{.*\}", response, re.DOTALL)
                parsed = json.loads(json_match.group()) if json_match else {}
            except Exception:
                parsed = {}
        else:
            parsed = {}

        if not parsed.get("summary"):
            parsed = {
                "summary": f"Aggregated {len(memories)} experiences for {task_type} at {', '.join(locations)} during {period}",
                "spatial_patterns": [f"Active area: {', '.join(locations)}"],
                "temporal_patterns": [f"Active period: {period}"],
                "reusable_insights": [f"Consistent {task_type} patterns observed"],
            }

        source_periods = set()
        for mem in memories:
            tc = _tc_from_any(mem.get("temporal_context"))
            if tc:
                source_periods.add(tc.period)

        tc_now = TemporalContext.from_datetime(datetime.now())
        return ReflectionEntry(
            id=str(uuid.uuid4()),
            summary=parsed.get("summary", ""),
            spatial_patterns=parsed.get("spatial_patterns", []),
            temporal_patterns=parsed.get("temporal_patterns", []),
            reusable_insights=parsed.get("reusable_insights", []),
            source_locations=locations,
            source_task_types=[task_type],
            source_periods=list(source_periods),
            source_ids=[str(id(m)) for m in memories],
            importance=0.8,
            temporal_context=tc_now.to_dict(),
            timestamp=datetime.now().isoformat(),
        )


def _extract_locations(mem: Dict) -> List[str]:
    locations: List[str] = []
    for key in ("location", "city"):
        val = mem.get(key)
        if isinstance(val, str) and val.strip():
            locations.append(val.strip().lower())
    task = mem.get("task", {})
    if isinstance(task, dict):
        for key in ("location", "city"):
            val = task.get(key)
            if isinstance(val, str) and val.strip():
                locations.append(val.strip().lower())
    return sorted(set(locations))


def _extract_task_type_flat(mem: Dict) -> str:
    if isinstance(mem.get("task_type"), str):
        return mem["task_type"]
    task = mem.get("task")
    if isinstance(task, dict) and isinstance(task.get("task_type"), str):
        return task["task_type"]
    return ""


# ── MemoryModule (v3 with ablation switches) ──────────────────────

class MemoryModule:
    """
    时空记忆模块 (v3)

    Ablation switches (all default True):
    - enable_temporal_context (C1): attach TemporalContext to stored memories
    - enable_actr_activation  (C2): use ACT-R activation scoring (vs token overlap)
    - enable_temporal_match   (C3): multi-granularity temporal matching (vs always-True)
    - enable_reflector        (C4): LLM-driven reflection compression
    - enable_pattern_detector (C5): statistical temporal pattern detection
    - enable_cube_retrieval   (C6): CubeGraph-inspired hierarchical cube retrieval
    """

    def __init__(
        self,
        config: Optional[Dict] = None,
        llm_client: Optional[Any] = None,
        enable_temporal_context: bool = True,
        enable_actr_activation: bool = True,
        enable_temporal_match: bool = True,
        enable_reflector: bool = True,
        enable_pattern_detector: bool = True,
        enable_cube_retrieval: bool = False,
    ):
        self.config = config or {}
        self.llm_client = llm_client

        # Ablation flags
        self.enable_temporal_context = enable_temporal_context
        self.enable_actr_activation = enable_actr_activation
        self.enable_temporal_match = enable_temporal_match
        self.enable_reflector = enable_reflector
        self.enable_pattern_detector = enable_pattern_detector
        self.enable_cube_retrieval = enable_cube_retrieval

        # 记忆存储
        self.working_memory: Dict[str, Any] = {}
        self.short_term_memory: deque = deque(maxlen=self.config.get("short_term_size", 100))
        self.long_term_memory: Dict[str, Any] = {
            "spatial": {},
            "temporal": {
                "by_period": {},
                "by_day_type": {"weekday": [], "weekend": []},
                "by_season": {},
            },
            "semantic": {},
            "reflections": [],
            "procedural": [],
        }
        self.feedback_log: List[Dict[str, Any]] = []

        # Core memory (persistent, self-edited)
        self.core_memory: Dict[str, str] = {
            "persona": "I am UrbanAgent, specializing in urban spatial analysis.",
            "temporal_patterns": "{}",
        }

        # 索引
        self.spatial_index: Dict[str, Any] = {}
        self.temporal_index: List[Dict] = []

        # Components
        self.reflector = MemoryReflector(llm_client=llm_client) if enable_reflector else None
        self.pattern_detector = TemporalPatternDetector() if enable_pattern_detector else None
        self.cube_retriever = (
            CubeGraphMemoryBackend(self.config.get("cube_retrieval_config"))
            if enable_cube_retrieval and CubeGraphMemoryBackend is not None else None
        )

    async def retrieve(self, query: Dict, query_time: Optional[datetime] = None) -> Dict[str, Any]:
        """检索相关记忆。query_time 可指定查询的虚拟时间（用于测试）。"""
        query_tc = TemporalContext.from_datetime(query_time or datetime.now()) if self.enable_temporal_context else None
        task_type = self._extract_task_type(query)

        context: Dict[str, Any] = {
            "working": self.working_memory,
            "relevant_short_term": [],
            "relevant_long_term": {},
            "best_match": None,
            "query_summary": self._summarize_query(query),
            "retrieval_trace": {"short_term": [], "long_term": []},
        }
        if self.enable_pattern_detector:
            context["temporal_patterns"] = self._get_temporal_patterns_for_query(query)

        # 从短期记忆中检索
        scored_short_term = []
        for memory in self.short_term_memory:
            if self.enable_actr_activation:
                score = self._activation_score(memory, query, query_tc, task_type)
            else:
                score = self._relevance_score(memory, query)
            if score > 0.3:
                scored_short_term.append((score, memory))
                context["retrieval_trace"]["short_term"].append({
                    "memory_id": memory.get("id"),
                    "score": round(score, 4),
                    "task_type": self._extract_task_type(memory),
                    "locations": self._extract_location_keys(memory),
                })
                # Retrieval strengthening for ACT-R
                if self.enable_actr_activation:
                    access_list = memory.get("access_timestamps")
                    if isinstance(access_list, list):
                        access_list.append(datetime.now().isoformat())

        scored_short_term.sort(key=lambda item: item[0], reverse=True)
        context["relevant_short_term"] = [memory for _, memory in scored_short_term[:5]]

        # 从长期记忆中检索
        context["relevant_long_term"] = self._retrieve_from_long_term(query, query_tc, task_type)
        context["retrieval_trace"]["long_term"] = {
            key: len(value) for key, value in context["relevant_long_term"].items()
            if isinstance(value, list)
        }
        all_matches = context["relevant_short_term"] + self._flatten_long_term_matches(context["relevant_long_term"])
        if all_matches:
            if self.enable_actr_activation:
                context["best_match"] = max(
                    all_matches,
                    key=lambda item: self._activation_score(item, query, query_tc, task_type),
                )
            else:
                context["best_match"] = max(
                    all_matches,
                    key=lambda item: self._relevance_score(item, query),
                )

        return context

    async def store(self, experience: Dict):
        """存储经验到记忆"""
        now = datetime.now()
        experience.setdefault("id", str(uuid.uuid4()))

        # Attach temporal context (C1) — respect pre-existing from seed data
        if self.enable_temporal_context:
            existing_tc = experience.get("temporal_context")
            if existing_tc is None:
                experience["temporal_context"] = TemporalContext.from_datetime(now)
            elif isinstance(existing_tc, dict):
                experience["temporal_context"] = _tc_from_any(existing_tc) or TemporalContext.from_datetime(now)

        # Add access tracking for ACT-R (C2)
        if self.enable_actr_activation:
            experience.setdefault("access_timestamps", [now.isoformat()])
            experience.setdefault("importance", 0.5)
            experience.setdefault("category", "observation")

        # 添加到工作记忆
        self.working_memory = experience

        # 添加到短期记忆
        self.short_term_memory.append({
            **experience,
            "timestamp": now.isoformat(),
        })

        # 更新长期记忆
        await self._update_long_term(experience)

        # Reflector check (C4)
        if self.enable_reflector and self.reflector:
            if await self.reflector.should_reflect(self.short_term_memory):
                reflections = await self.reflector.reflect(self.short_term_memory)
                for ref in reflections:
                    reflection = ref.__dict__ if hasattr(ref, "__dict__") else ref
                    self.long_term_memory["reflections"].append(reflection)
                    self.long_term_memory["procedural"].append(self._reflection_to_procedural_strategy(reflection))
                self.long_term_memory["reflections"] = self.long_term_memory["reflections"][-50:]
                self.long_term_memory["procedural"] = self.long_term_memory["procedural"][-50:]

        logger.info("Experience stored in memory")

    # ── ACT-R Activation Score (C2) ──

    def _activation_score(
        self,
        memory: Dict,
        query: Dict,
        query_tc: Optional[TemporalContext] = None,
        task_type: str = "",
    ) -> float:
        """ACT-R inspired spatio-temporal activation score."""
        base_level = self._actr_base_level(memory)
        spatial_proximity = self._spatial_score(memory, query)

        temporal_relevance = 0.0
        if self.enable_temporal_match:
            memory_tc = memory.get("temporal_context")
            if memory_tc is not None and query_tc is not None:
                granularity = _TASK_GRANULARITY.get(task_type, "any")
                temporal_relevance = temporal_match(memory_tc, query_tc, granularity)
            temporal_relevance += self._temporal_recency(memory)

        importance = float(memory.get("importance", 0.5))
        category = memory.get("category", "observation")
        category_weight = _CATEGORY_WEIGHT.get(category, 0.5)

        return (
            base_level * 0.2
            + spatial_proximity * 0.3
            + temporal_relevance * 0.25
            + importance * 0.1
            + category_weight * 0.15
        )

    def _actr_base_level(self, memory: Dict) -> float:
        """ACT-R base-level activation: ln(Σ t_i^(-d)), d=0.5"""
        access_timestamps = memory.get("access_timestamps", [])
        if not access_timestamps:
            ts_str = memory.get("timestamp")
            access_timestamps = [ts_str] if ts_str else []
        if not access_timestamps:
            return 0.0

        now = datetime.now()
        d = 0.5
        total = 0.0
        for ts_str in access_timestamps:
            try:
                ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str
                if not isinstance(ts, datetime):
                    continue
                delta_hours = max((now - ts).total_seconds() / 3600.0, 0.01)
                total += delta_hours ** (-d)
            except (ValueError, TypeError):
                continue
        return math.log(max(total, 1e-10)) if total > 0 else -5.0

    def _spatial_score(self, memory: Dict, query: Dict) -> float:
        memory_tokens = _tokenize_text(memory)
        query_tokens = _tokenize_text(query)
        if not query_tokens:
            return 0.0
        matches = len(memory_tokens & query_tokens)
        token_score = matches / len(query_tokens)
        query_locations = set(self._extract_location_keys(query))
        memory_locations = set(self._extract_location_keys(memory))
        location_bonus = 0.3 if query_locations & memory_locations else 0.0
        return token_score + location_bonus

    def _temporal_recency(self, memory: Dict) -> float:
        ts_str = memory.get("timestamp")
        if not ts_str:
            return 0.0
        try:
            ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str
            delta_days = max((datetime.now() - ts).total_seconds() / 86400.0, 0.001)
        except (ValueError, TypeError):
            return 0.0
        category = memory.get("category", "observation")
        lam = _CATEGORY_DECAY.get(category, 0.05)
        return math.exp(-lam * delta_days)

    # ── Original relevance score (fallback when C2 disabled) ──

    def _relevance_score(self, memory: Dict, query: Dict) -> float:
        memory_tokens = _tokenize_text(memory)
        query_tokens = _tokenize_text(query)
        if not query_tokens:
            return 0.0

        matches = len(memory_tokens & query_tokens)
        token_score = matches / len(query_tokens)

        query_locations = set(self._extract_location_keys(query))
        memory_locations = set(self._extract_location_keys(memory))
        location_bonus = 0.3 if query_locations & memory_locations else 0.0

        query_type = self._extract_task_type(query)
        memory_type = self._extract_task_type(memory)
        type_bonus = 0.2 if query_type and query_type == memory_type else 0.0

        return token_score + location_bonus + type_bonus

    def _is_relevant(self, memory: Dict, query: Dict) -> bool:
        return self._relevance_score(memory, query) > 0.3

    def _retrieve_from_long_term(
        self,
        query: Dict,
        query_tc: Optional[TemporalContext] = None,
        task_type: str = "",
    ) -> Dict:
        """从长期记忆中检索"""
        results: Dict[str, list] = {
            "spatial": [],
            "temporal": [],
            "semantic": [],
            "reflections": [],
            "procedural": [],
            "cube_rag": [],
        }

        # 空间检索
        query_locations = self._extract_location_keys(query)
        for location in query_locations:
            for key, value in self.long_term_memory["spatial"].items():
                if location in key:
                    results["spatial"].extend(value)

        # 时间检索 (v3: temporal bucket retrieval)
        if self.enable_temporal_match and query_tc is not None:
            temporal_data = self.long_term_memory.get("temporal", {})
            period_bucket = temporal_data.get("by_period", {}).get(query_tc.period, [])
            results["temporal"].extend(period_bucket[-5:])
            day_type = "weekend" if query_tc.is_weekend else "weekday"
            day_bucket = temporal_data.get("by_day_type", {}).get(day_type, [])
            results["temporal"].extend(day_bucket[-5:])
            season_bucket = temporal_data.get("by_season", {}).get(query_tc.season, [])
            results["temporal"].extend(season_bucket[-3:])
        elif "time" in query:
            time_query = query["time"]
            for entry in self.temporal_index:
                if self._time_match(entry["time"], time_query):
                    results["temporal"].append(entry)

        # 语义检索
        query_type = self._extract_task_type(query) or query.get("type", "")
        if query_type in self.long_term_memory["semantic"]:
            results["semantic"] = self.long_term_memory["semantic"][query_type][-5:]

        # Reflections
        if self.enable_reflector:
            for ref in self.long_term_memory.get("reflections", [])[-5:]:
                if isinstance(ref, dict):
                    ref_locations = ref.get("source_locations", [])
                    if set(query_locations) & set(ref_locations):
                        results["reflections"].append(ref)

        for strategy in self.long_term_memory.get("procedural", [])[-5:]:
            if not isinstance(strategy, dict):
                continue
            strategy_locations = set(strategy.get("trigger_locations", []))
            strategy_tasks = set(strategy.get("trigger_task_types", []))
            if (query_locations and set(query_locations) & strategy_locations) or (task_type and task_type in strategy_tasks):
                results["procedural"].append(strategy)

        if self.enable_cube_retrieval and self.cube_retriever:
            results["cube_rag"] = self.cube_retriever.search(
                query,
                query_tc=query_tc.to_dict() if isinstance(query_tc, TemporalContext) else normalize_temporal_context(query_tc),
                task_type=task_type,
            )

        return results

    def _reflection_to_procedural_strategy(self, reflection: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": f"strategy:{reflection.get('id', str(uuid.uuid4()))}",
            "source_reflection_id": reflection.get("id"),
            "summary": reflection.get("summary", ""),
            "trigger_locations": reflection.get("source_locations", []),
            "trigger_task_types": reflection.get("source_task_types", []),
            "reusable_steps": reflection.get("reusable_insights", []),
            "importance": reflection.get("importance", 0.7),
            "timestamp": reflection.get("timestamp", datetime.now().isoformat()),
        }

    def apply_feedback(self, feedback: Dict[str, Any]) -> bool:
        memory_id = feedback.get("memory_id")
        if not memory_id:
            return False

        applied = False
        for memory in self.short_term_memory:
            if isinstance(memory, dict) and memory.get("id") == memory_id:
                memory["importance"] = max(0.0, min(1.0, float(memory.get("importance", 0.5)) + float(feedback.get("importance_delta", 0.0))))
                memory.setdefault("feedback", []).append(feedback)
                applied = True

        if applied:
            record = {**feedback, "timestamp": datetime.now().isoformat()}
            self.feedback_log.append(record)
        return applied

    def inspect_state(self) -> Dict[str, Any]:
        return {
            "working_memory_size": len(self.working_memory),
            "short_term_size": len(self.short_term_memory),
            "feedback_count": len(self.feedback_log),
            "procedural_strategy_count": len(self.long_term_memory.get("procedural", [])),
        }

    async def _update_long_term(self, experience: Dict):
        """更新长期记忆"""
        perception = experience.get("perception", {})
        timestamp = datetime.now().isoformat()
        tc = experience.get("temporal_context")

        # Spatial indexing
        for location_key in self._extract_location_keys(experience):
            self.long_term_memory["spatial"].setdefault(location_key, []).append({
                "location": location_key,
                "experience": experience,
                "timestamp": timestamp,
            })
            self.long_term_memory["spatial"][location_key] = self.long_term_memory["spatial"][location_key][-10:]

        if "bounds" in perception:
            bounds = perception["bounds"]
            bbox_key = f"bbox:{bounds.get('min_lon', 0)}_{bounds.get('min_lat', 0)}"
            self.long_term_memory["spatial"].setdefault(bbox_key, []).append({
                "bounds": bounds,
                "experience": experience,
                "timestamp": timestamp,
            })
            self.long_term_memory["spatial"][bbox_key] = self.long_term_memory["spatial"][bbox_key][-10:]

        # Temporal bucket indexing (v3, C1)
        if self.enable_temporal_context and tc is not None:
            tc_obj = _tc_from_any(tc)
            if tc_obj:
                entry = {
                    "experience": experience,
                    "timestamp": timestamp,
                    "temporal_context": tc_obj.to_dict(),
                }
                period_key = tc_obj.period
                self.long_term_memory["temporal"]["by_period"].setdefault(period_key, []).append(entry)
                self.long_term_memory["temporal"]["by_period"][period_key] = \
                    self.long_term_memory["temporal"]["by_period"][period_key][-20:]

                day_type = "weekend" if tc_obj.is_weekend else "weekday"
                self.long_term_memory["temporal"]["by_day_type"].setdefault(day_type, []).append(entry)
                self.long_term_memory["temporal"]["by_day_type"][day_type] = \
                    self.long_term_memory["temporal"]["by_day_type"][day_type][-20:]

                season_key = tc_obj.season
                self.long_term_memory["temporal"]["by_season"].setdefault(season_key, []).append(entry)
                self.long_term_memory["temporal"]["by_season"][season_key] = \
                    self.long_term_memory["temporal"]["by_season"][season_key][-20:]

        # Legacy temporal index
        self.temporal_index.append({
            "time": datetime.now(),
            "experience": experience,
        })

        # Semantic indexing
        semantic_key = self._extract_task_type(experience) or perception.get("type") or experience.get("type")
        if semantic_key:
            self.long_term_memory["semantic"].setdefault(semantic_key, []).append({
                "experience": experience,
                "timestamp": timestamp,
            })
            self.long_term_memory["semantic"][semantic_key] = \
                self.long_term_memory["semantic"][semantic_key][-20:]

        if len(self.temporal_index) > 1000:
            self.temporal_index = self.temporal_index[-1000:]

        if self.enable_cube_retrieval and self.cube_retriever:
            self.cube_retriever.index_entry({
                "experience": experience,
                "timestamp": timestamp,
                "temporal_context": normalize_temporal_context(tc),
            })

        # Pattern detection (C5)
        if self.enable_pattern_detector and self.pattern_detector:
            self._run_pattern_detection(experience)

    def _run_pattern_detection(self, experience: Dict) -> None:
        locations = self._extract_location_keys(experience)
        task_type = self._extract_task_type(experience)
        if not locations or not task_type:
            return
        location = locations[0]

        relevant_memories = [
            mem for mem in self.short_term_memory
            if isinstance(mem, dict)
            and location in self._extract_location_keys(mem)
            and self._extract_task_type(mem) == task_type
        ]
        pattern = self.pattern_detector.detect_patterns(relevant_memories, location, task_type)
        if pattern:
            try:
                patterns_dict = json.loads(self.core_memory.get("temporal_patterns", "{}"))
            except (json.JSONDecodeError, TypeError):
                patterns_dict = {}
            key = f"{location}_{task_type}"
            patterns_dict[key] = {
                "peak_periods": pattern.peak_periods,
                "weekday_vs_weekend": pattern.weekday_vs_weekend,
                "seasonal_trend": pattern.seasonal_trend,
                "monotonic_trend": pattern.monotonic_trend,
                "sample_count": pattern.sample_count,
                "confidence": pattern.confidence,
            }
            self.core_memory["temporal_patterns"] = json.dumps(patterns_dict, ensure_ascii=False)

    def _get_temporal_patterns_for_query(self, query: Dict) -> Dict:
        try:
            all_patterns = json.loads(self.core_memory.get("temporal_patterns", "{}"))
        except (json.JSONDecodeError, TypeError):
            return {}
        locations = self._extract_location_keys(query)
        task_type = self._extract_task_type(query)
        relevant: Dict[str, Any] = {}
        for loc in locations:
            key = f"{loc}_{task_type}" if task_type else loc
            if key in all_patterns:
                relevant[key] = all_patterns[key]
        return relevant

    def _time_match(self, time1: Any, time2: Any) -> bool:
        """Legacy time matching (always True)"""
        return True

    def _extract_location_keys(self, payload: Any) -> List[str]:
        if not isinstance(payload, dict):
            return []
        values = []
        for key in ("location", "city", "start", "end"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value.strip().lower())
        task = payload.get("task")
        if isinstance(task, dict):
            values.extend(self._extract_location_keys(task))
        perception = payload.get("perception")
        if isinstance(perception, dict):
            values.extend(self._extract_location_keys(perception))
        return sorted(set(values))

    def _extract_task_type(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        if isinstance(payload.get("task_type"), str):
            return payload["task_type"]
        task = payload.get("task")
        if isinstance(task, dict) and isinstance(task.get("task_type"), str):
            return task["task_type"]
        return ""

    def _flatten_long_term_matches(self, matches: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        flattened = []
        for value in matches.values():
            if isinstance(value, list):
                flattened.extend(item for item in value if isinstance(item, dict))
        return flattened

    def _summarize_query(self, query: Dict) -> Dict[str, Any]:
        return {
            "task_type": self._extract_task_type(query),
            "locations": self._extract_location_keys(query),
        }

    def clear_working_memory(self):
        """清空工作记忆"""
        self.working_memory = {}
        logger.info("Working memory cleared")

    def get_memory_stats(self) -> Dict:
        """获取记忆统计"""
        temporal = self.long_term_memory.get("temporal", {})
        temporal_count = sum(
            len(v)
            for bucket in temporal.values()
            for v in (bucket.values() if isinstance(bucket, dict) else [bucket])
            if isinstance(v, list)
        )
        try:
            pattern_count = len(json.loads(self.core_memory.get("temporal_patterns", "{}")))
        except (json.JSONDecodeError, TypeError):
            pattern_count = 0

        return {
            "working_memory_size": len(self.working_memory),
            "short_term_size": len(self.short_term_memory),
            "long_term_spatial": len(self.long_term_memory["spatial"]),
            "long_term_temporal": temporal_count,
            "long_term_semantic": len(self.long_term_memory["semantic"]),
            "reflections_count": len(self.long_term_memory.get("reflections", [])),
            "procedural_strategy_count": len(self.long_term_memory.get("procedural", [])),
            "pattern_count": pattern_count,
            "cube_retrieval": self.cube_retriever.get_stats() if self.cube_retriever else {},
            "ablation_flags": {
                "temporal_context": self.enable_temporal_context,
                "actr_activation": self.enable_actr_activation,
                "temporal_match": self.enable_temporal_match,
                "reflector": self.enable_reflector,
                "pattern_detector": self.enable_pattern_detector,
                "cube_retrieval": self.enable_cube_retrieval,
            },
        }

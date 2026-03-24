# UrbanWorkflowBench Benchmark Card

## Summary

UrbanWorkflowBench evaluates urban agents as workflow systems rather than answer-only predictors.

Compared with CityBench, it adds protocol-level probes for:

1. dual-space cognition
2. memory continuity
3. tool orchestration
4. human-in-the-loop checkpoints

## Why This Benchmark Exists

CityBench is useful for external comparability, but it does not fully expose the workflow-level claims of UrbanAgent.

UrbanWorkflowBench is designed to answer a different question:

Can an urban agent correctly build spatial structure, reuse prior place-based context, orchestrate tools, and remain controllable through human checkpoints?

## Suite Overview

### 1. external_citydata_subset

Design motive:

1. preserve comparability with existing city-task benchmarks
2. retain familiar task formats for geoqa, mobility, navigation, and exploration

Scoring:

1. exact match on task-specific outputs
2. suite score is the average case score

Difference from CityBench:

1. uses a configurable subset rather than the full eight-task spread
2. is embedded into a mixed protocol benchmark rather than standing alone

### 2. dual_space_design

Design motive:

1. test whether topology and vector geometry are jointly useful
2. measure relation-sensitive spatial structure instead of only final answers

Scoring:

1. relation accuracy
2. mapping completeness recorded as a supporting signal

Difference from CityBench:

1. directly probes internal spatial representation claims
2. does not depend on a large model backend to show architectural sensitivity

### 3. memory_continuity

Design motive:

1. test repeated-task transfer
2. check whether place-based prior experience changes later reasoning

Scoring:

1. exact match on the repeated-task prediction or decision
2. retrieval summary recorded for inspection

Difference from CityBench:

1. CityBench mostly evaluates isolated tasks
2. this suite evaluates continuity across tasks

### 4. tool_orchestration

Design motive:

1. test whether tool plans use valid tools in a sensible order
2. test whether failure can be contained and recovered from

Scoring:

1. tool sequence match
2. valid call rate
3. workflow completion
4. recovery success when failure is injected

Difference from CityBench:

1. CityBench measures task outcomes, not tool workflow quality
2. this suite exposes whether an agent can execute structured geospatial tool pipelines

### 5. hitl_checkpoint

Design motive:

1. test whether human checkpoints can modify, reject, or redirect execution
2. test whether checkpoint actions persist into final state

Scoring:

1. checkpoint compliance
2. modification persistence
3. cancellation handling when applicable

Difference from CityBench:

1. CityBench has no explicit human checkpoint protocol
2. this suite evaluates controllability, not only autonomy

## Recommended Usage

1. Use provider none for local smoke tests.
2. Use provider qwen or kimi for formal external scoring.
3. Use provider all for full benchmark sweeps when environment variables are configured.

## Limitations

1. v1.1 tool orchestration probes are synthetic but executable.
2. v1.1 hitl probes simulate checkpoint behavior using explicit policies rather than a live browser session.
3. v1.1 remains a benchmark scaffold and should expand toward richer workflow datasets in later versions.
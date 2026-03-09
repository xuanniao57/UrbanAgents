# UrbanAgent CEUS Draft: Citation Gaps and 30 Candidate References

Generated on 2026-03-08 using the zotero-literature-scout workflow, with results saved under artifacts/literature_search/ceus_citation_boost.

## 1. Main Citation Gaps

### Gap A. Intro paragraph on LLM capability and agent orchestration

Current issue:
- The paragraph around the introduction currently leans on weak or non-paper citations such as OpenAI 2023, Anthropic 2024, AutoGPT, and LangChain repo-style references.
- For a CEUS submission, this should be anchored by formal papers on reasoning, tool use, and multi-agent orchestration.

Suggested insertion point:
- Replace or supplement the claim block in UrbanAgent_CEUS_Draft.md around the introduction paragraph that starts with "Meanwhile, Large Language Models..."

### Gap B. Research gap on spatial structure reasoning

Current issue:
- The claims about topological and geometric reasoning being missing in existing urban LLM systems are directionally right, but the supporting literature is still thin.
- This section needs formal spatial reasoning, scene graph, and geospatial reasoning papers.

Suggested insertion point:
- Research gap 2 and the dual-space contribution paragraph.

### Gap C. Related work on geospatial and urban LLM systems

Current issue:
- The geospatial related-work section still contains uncertain or thinly verified items such as ShapefileGPT and older placeholder-style citations.
- It needs more formal benchmark, geospatial, and urban LLM references.

Suggested insertion point:
- Section 2.2 and Table 1 positioning discussion.

### Gap D. Multimodal urban perception and urban data modalities

Current issue:
- Section 3.2 makes strong claims about why street view, remote sensing, trajectories, and open geospatial data are complementary.
- The logic is good, but the paragraph needs more support from multimodal urban sensing and trajectory survey literature.

Suggested insertion point:
- Section 3.2 opening paragraph and the trajectory-data paragraph.

### Gap E. Memory and human-in-the-loop planning support

Current issue:
- The memory section and the six decision-point interaction section would benefit from more than one or two citations.
- In particular, the planning-support lineage and human-AI collaboration claims should be backed by planning support systems and urban-planning-AI papers.

Suggested insertion point:
- Section 2.4, Section 3.3 memory discussion, and Section 3.4 human-AI collaboration.

### Gap F. Placeholder references that should be replaced or cross-checked first

Priority items:
- OpenAI, 2023 [?]
- Anthropic, 2024 [?]
- Auto-GPT, 2023 [?]
- LangChain, 2022 [?]
- greenR, 2024 [?]
- ShapefileGPT, 2024 [?]
- Yang et al., 2018 [?]
- Park et al., 2023 [?]
- Zheng, 2015 [?]

## 2. Recommended 30 References

Rule applied here:
- Only formally published or formally accepted journal/conference papers are retained.
- If a paper also circulated on arXiv, it is only included here when a journal or conference venue is available.

### A. Formal replacements for weak agent-foundation citations

1. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023.
   Use for: LLMs can interleave reasoning and tool-mediated action.

2. Toolformer: Language Models Can Teach Themselves to Use Tools. NeurIPS 2023.
   Use for: LLM tool-use capability and API invocation learning.

3. AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. COLM 2024.
   Use for: multi-agent orchestration and role-based collaboration.

4. MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework. ICLR 2024.
   Use for: software-task decomposition and structured multi-agent workflows.

5. Gorilla: Large Language Model Connected with Massive APIs. NeurIPS 2023.
   Use for: tool grounding and API-scale tool use.

6. Generative Agents: Interactive Simulacra of Human Behavior. UIST 2023. DOI: 10.1145/3586183.3606763
   Use for: memory, reflection, and long-horizon agent behavior.

7. Avatar: Optimizing LLM Agents for Tool Usage via Contrastive Reasoning. NeurIPS 2024. DOI: 10.52202/079017-0817
   Use for: stronger evidence that tool-use performance depends on structured reasoning design.

### B. Urban and geospatial LLM systems, benchmarks, and reviews

8. CityBench: Evaluating the Capabilities of Large Language Models for Urban Tasks. 2025. DOI: 10.1145/3711896.3737375
   Use for: benchmark background and urban task taxonomy.

9. ChatGeoAI: Enabling Geospatial Analysis for Public through Natural Language, with Large Language Models. ISPRS International Journal of Geo-Information, 2024. DOI: 10.3390/ijgi13100348
   Use for: geospatial natural-language analysis systems.

10. Evaluating Large Language Models on Geospatial Tasks: A Multiple Geospatial Task Benchmarking Study. International Journal of Digital Earth, 2025. DOI: 10.1080/17538947.2025.2480268
   Use for: broader geospatial benchmark framing beyond CityBench.

11. Urban Computing in the Era of Large Language Models. ACM Transactions, 2025. DOI: 10.1145/3768163
   Use for: positioning UrbanAgent inside the urban-LLM research landscape.

12. GeoAgent: A Hierarchical LLM-Based Multi-Agent Architecture for Autonomous Spatial Analysis. International Journal of Geographical Information Science, 2026. DOI: 10.1080/13658816.2026.2624784
   Use for: closest related geospatial agent system.

13. Agentic LLM Framework for Generating Spatial Intelligence to Support Decision-Making in Smart Cities. SIGSPATIAL workshop, 2025. DOI: 10.1145/3764924.3770899
   Use for: smart-city decision support with spatially grounded agent design.

14. Multi-agent Geospatial Copilots for Remote Sensing Workflows. IGARSS 2025. DOI: 10.1109/IGARSS55030.2025.11243915
   Use for: recent connector-style geospatial workflow orchestration.

15. Unleashing the Potential of Large Language Models in Urban Data Analytics: A Review of Emerging Innovations and Future Research. Smart Cities, 2025. DOI: 10.3390/smartcities8060201
   Use for: review support in Section 2 and Introduction.

16. GeoJSON Agents: A Multi-Agent LLM Architecture for Geospatial Analysis - Function Calling vs. Code Generation. Big Earth Data, 2026. DOI: 10.1080/20964471.2026.2615511
   Use for: function-calling vs code-generation comparison in geospatial analysis.

### C. Spatial reasoning, scene graphs, and topology-aware representations

17. Graph R-CNN for Scene Graph Generation. ECCV 2018.
   Use for: classic scene-graph reference replacing the current uncertain placeholder.

18. LLaVA-SpaceSGG: Visual Instruct Tuning for Open-Vocabulary Scene Graph Generation with Enhanced Spatial Relations. WACV 2025. DOI: 10.1109/WACV61041.2025.00620
   Use for: spatial scene graphs in modern VLMs.

19. SpatialVLM: Endowing Vision-Language Models with Spatial Reasoning Capabilities. CVPR 2024. DOI: 10.1109/CVPR52733.2024.01370
   Use for: VLM spatial reasoning support.

20. TopViewRS: Vision-Language Models as Top-View Spatial Reasoners. EMNLP 2024. DOI: 10.18653/v1/2024.emnlp-main.106
   Use for: spatial reasoning from map-like or top-view contexts.

21. Foundation Models for Geospatial Reasoning: Assessing the Capabilities of Large Language Models in Understanding Geometries and Topological Spatial Relations. International Journal of Geographical Information Science, 2025. DOI: 10.1080/13658816.2025.2511227
   Use for: direct support for the topology-vs-metric reasoning gap.

22. SpatialGPT: Zero-Shot Vision-and-Language Navigation via Spatial CoT over Structured Spatial Memory. ACM conference paper, 2025. DOI: 10.1145/3748636.3762753
   Use for: structured spatial memory and action reasoning.

### D. Multimodal urban perception, open data, and trajectory evidence

23. Integrating Street Views, Satellite Imageries and Remote Sensing Data into Economics and the Social Sciences. Social Science Computer Review, 2024. DOI: 10.1177/08944393231178604
   Use for: multimodal urban data integration.

24. Predicting Perceptions of the Built Environment Using GIS, Satellite and Street View Image Approaches. Landscape and Urban Planning, 2021. DOI: 10.1016/j.landurbplan.2021.104257
   Use for: why street view and overhead data should be combined.

25. Crowdsourced Geospatial Data Is Reshaping Urban Sciences. International Journal of Applied Earth Observation and Geoinformation, 2024. DOI: 10.1016/j.jag.2024.103687
   Use for: open data and crowdsourced urban science framing.

26. Social Sensing from Street-Level Imagery: A Case Study in Learning Spatio-Temporal Urban Mobility Patterns. ISPRS Journal of Photogrammetry and Remote Sensing, 2019. DOI: 10.1016/j.isprsjprs.2019.04.017
   Use for: street-view imagery linked to urban mobility and activity.

27. A Survey on Trajectory Data Management, Analytics, and Learning. ACM Computing Surveys, 2021. DOI: 10.1145/3440207
   Use for: replacing the weak trajectory placeholder and supporting Section 3.2.

28. Trajectory Data Mining: A Review of Methods and Applications. Journal of Spatial Information Science, 2016. DOI: 10.5311/JOSIS.2016.13.263
   Use for: broader trajectory-mining background if you want one classic survey plus one recent survey.

### E. Memory, planning support systems, and human-AI collaboration

29. HiAgent: Hierarchical Working Memory Management for Solving Long-Horizon Agent Tasks with Large Language Model. ACL 2025 Long Papers. DOI: 10.18653/v1/2025.acl-long.1575
   Use for: hierarchical working-memory design in long-horizon agents.

30. The Pathway of Urban Planning AI: From Planning Support to Plan-Making. 2024. DOI: 10.1177/0739456X231180568
   Use for: situating your human-in-the-loop and planning-support framing in current planning discourse.

31. Use of a Collaborative GIS-Based Planning-Support System to Assist in Formulating a Sustainable-Development Scenario for Hervey Bay, Australia. Environment and Planning B, 2005. DOI: 10.1068/b31109
   Use for: classic planning-support-system lineage behind your decision checkpoints.

32. Evolving from Rules to Learning in Urban Modeling and Planning Support Systems. Urban Science, 2025. DOI: 10.3390/urbansci9120508
   Use for: planning support systems evolving toward learning-based systems.

33. Artificial Intelligence Adoption in Urban Planning Governance: A Systematic Review of Advancements in Decision-Making, and Policy Making. Landscape and Urban Planning, 2025. DOI: 10.1016/j.landurbplan.2025.105337
   Use for: human-AI collaboration and governance framing.

34. Towards Responsible Urban Geospatial AI: Insights from the White and Grey Literatures. 2024. DOI: 10.1007/s41651-024-00184-2
   Use for: responsible and inspectable urban geospatial AI.

## 3. Recommended Cut to Exactly 30

If you want a hard cap of 30 additions, keep items 1-30 above and treat items 31-34 as backup references.

Most useful backups:
- 31 if you want a classic PSS citation in addition to the planning-AI paper.
- 33 if the human-in-the-loop section is expanded.
- 34 if you want an ethics or responsibility citation in Discussion.

## 4. Best Immediate Replacements in the Draft

Replace these weak placeholders first:
- OpenAI, 2023 [?] -> ReAct + Toolformer + AutoGen
- Anthropic, 2024 [?] -> AutoGen + Avatar
- Auto-GPT, 2023 [?] -> ReAct + MetaGPT + AutoGen
- LangChain, 2022 [?] -> Toolformer + Gorilla
- Yang et al., 2018 [?] -> Graph R-CNN
- Park et al., 2023 [?] -> Generative Agents
- Zheng, 2015 [?] -> ACM CSUR 2021 trajectory survey + JOSIS 2016 survey

## 5. Saved Search Outputs

Raw and ranked results are stored under:
- artifacts/literature_search/ceus_citation_boost/agent_frameworks
- artifacts/literature_search/ceus_citation_boost/urban_geospatial_agents
- artifacts/literature_search/ceus_citation_boost/spatial_reasoning
- artifacts/literature_search/ceus_citation_boost/agent_memory
- artifacts/literature_search/ceus_citation_boost/human_ai_planning
- artifacts/literature_search/ceus_citation_boost/urban_data_modalities
- artifacts/literature_search/ceus_citation_boost/agent_core_papers
- artifacts/literature_search/ceus_citation_boost/planning_support_classics
- artifacts/literature_search/ceus_citation_boost/trajectory_classics
- artifacts/literature_search/ceus_citation_boost/specific_tools

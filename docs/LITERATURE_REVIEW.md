# 城市分析智能体系统：文献综述与研究框架

## 1. Introduction

### 1.1 研究背景

随着城市化进程的加速，城市空间变得越来越复杂，传统的城市分析方法面临着数据碎片化、分析维度单一、决策效率低下等挑战。近年来，大语言模型（Large Language Models, LLMs）和多模态大语言模型（Vision-Language Models, VLMs）的快速发展为城市智能分析提供了新的可能性。这些模型具备强大的语义理解、知识推理和多模态融合能力，为构建能够自主感知、理解和推理城市空间的智能体系统奠定了基础。

城市空间感知与推理涉及多种数据源的综合分析，包括遥感影像、街景图像、OpenStreetMap（OSM）数据、GeoJSON矢量数据、轨迹数据等。如何有效整合这些异构数据，构建能够进行空间感知、推理和决策的智能体系统，成为当前城市计算领域的重要研究方向。

### 1.2 研究意义

本研究旨在构建一个基于Agent框架的城市分析智能体系统，通过整合MCP（Model Context Protocol）、技能工具（Skills/Tools）和记忆管理框架，实现对多源城市数据的空间感知和推理。该系统将在CityBench、UrbanBench等城市任务基准测试上验证其有效性，为城市规划、管理和决策提供智能化支持。

本研究的意义体现在以下几个方面：
- **理论意义**：探索LLM/VLM在城市空间感知与推理中的应用边界，构建城市分析智能体的理论框架
- **方法意义**：提出多源数据融合、场景图生成、空间推理的集成方法
- **实践意义**：为城市规划师、管理者提供智能化的分析工具和决策支持

---

## 2. Literature Review

### 2.1 大语言模型在城市分析中的应用

#### 2.1.1 城市任务基准测试

**CityBench**（Feng et al., 2024）是首个系统评估大语言模型城市任务能力的基准测试平台。该研究构建了CityData数据集整合多样化城市数据，开发了CitySimu模拟器模拟细粒度城市动态，并设计了8个代表性城市任务，涵盖感知理解（perception-understanding）和决策制定（decision-making）两大类别。研究发现，先进的LLM和VLM在需要常识和语义理解的任务上表现良好，但在需要专业知识和高级推理能力的挑战性任务上表现不佳。

**Urban Planning LLM Evaluation**（Zhao et al., 2025）对OpenAI o1模型在城市规划领域的性能进行了全面评估，构建了包含556个任务的基准测试，涵盖城市规划文档、考试、数据分析、AI算法支持和论文写作五个关键类别。研究发现o1在领域知识掌握、基本操作能力和编码能力方面表现优异，但在城市设计、空间推理和高级专业考试方面存在局限性。

**USTBench**（Lai et al., 2025）作为城市智能体的时空推理基准测试，系统性地解剖了LLM作为城市智能体的时空推理能力。

**GeoAnalystBench**（Zhang et al., 2025）是评估大语言模型空间分析工作流和代码生成能力的GeoAI基准测试。

**GeoBenchX**（Krechetova & Kochedykov, 2025）用于基准测试LLM在解决多步地理空间任务中的智能体能力。

#### 2.1.2 多智能体城市分析系统

**AutoBEE**（Quan et al., 2025）提出了一个基于层次化多智能体系统的建筑能耗与环境参数自动分析框架。该框架通过开发综合智能体工具库、建立从团队到智能体的多级网络、设计轻量级通信协议和创建动态路径规划，实现了从自然语言输入到建筑性能报告输出的自主无人操作。

**CartoAgent**（Wang et al., 2025）是一个基于多模态大语言模型的多智能体制图框架，用于地图样式转换和评估。该研究展示了多智能体协作在地理信息科学中的应用潜力。

**OpenCity**（Yan et al., 2024）是一个可扩展平台，使用大规模LLM智能体模拟城市活动，为城市动态建模提供了新的范式。

**LLM Agents for Smart City Management**（Kalyuzhnaya et al., 2025）探索了通过多智能体AI系统增强智慧城市管理的决策支持。

**Multi-Agent Geospatial Copilots**（Lee et al., 2025）提出了用于遥感工作流的多智能体地理空间协作者系统。

### 2.2 地理空间智能体与代码生成

#### 2.2.1 地理空间代码生成智能体

**GeoCogent**（Hou et al., 2025）是一个基于LLM的地理空间代码生成智能体，能够自动生成处理地理空间数据的代码，显著提高了地理空间分析的效率。

**GeoJSON Agents**（Luo et al., 2025, 2026）提出了多智能体LLM架构用于地理空间分析，比较了函数调用与代码生成两种方法的优劣。该研究为GeoJSON数据的自动化处理提供了有效的解决方案。

**ShapefileGPT**（Lin et al., 2024）是一个多智能体大语言模型框架，用于自动化Shapefile数据处理，支持复杂地理空间数据格式的智能分析。

**An LLM Agent for Automatic Geospatial Data Analysis**（Chen et al., 2024）提出了自动地理空间数据分析的LLM智能体，展示了LLM在地理空间领域的应用潜力。

#### 2.2.2 地图与空间推理智能体

**MapAgent**（Hasan et al., 2025）是一个层次化智能体，通过动态地图工具集成实现地理空间推理，支持复杂的地图查询和分析任务。

**CompassLLM**（Ananto et al., 2025）提出了多智能体方法用于地理空间推理和热门路径查询，为导航和路径规划提供了智能解决方案。

**Spatial-Agent**（Bao et al., 2026）基于科学核心概念实现智能体地理空间推理，通过引入领域知识增强了空间推理的准确性。

**CityGPT**（Feng et al., 2024）增强了大语言模型的城市空间认知能力，为城市尺度的空间理解提供了基础。

### 2.3 多源城市数据融合与感知

#### 2.3.1 多模态数据融合

**STG4DUF**（Cao et al., 2025）提出了时空图动态城市功能框架，结合多模态数据融合和自监督学习来揭示无标签的动态城市功能。该框架通过双分支编码器和动态图架构整合街景图像、建筑矢量数据、POI和基于手机的人类轨迹数据，实现了地块级功能模式及其时间动态的提取。

**多源感知研究**表明，城市环境体验涉及多种感官模态——视觉、听觉、嗅觉、触觉和味觉。Kavee & Flanigan（2025）通过系统综述量化了城市形态的多感官感知，重新诠释了Lynch的城市元素分类法作为组织和分析多感官感知的框架。

#### 2.3.2 街景图像分析

街景图像已成为城市感知研究的重要数据源。Sun et al.（2023）提出了基于场景图生成（Scene Graph Generation, SGG）的街景感知改进建议方法，使用SimGNN图匹配算法识别与高评分街景图结构高度相似的参考图像。

**空间迷失研究**（Yang et al., 2026）开发了多尺度、数据驱动的框架，将局部视觉感知属性（如天空可见度、场景开放度、行人密度）与全局空间结构指标（如道路曲率、道路类型、土地利用模式）联系起来，基于多源地理空间数据和图像语义分割来量化迷失风险的环境决定因素。

#### 2.3.3 空间数据集成能力评估

**Can Large Language Models Integrate Spatial Data?**（Han et al., 2025）实证研究了LLM在空间数据集成中的推理优势和计算弱点，为理解LLM的地理空间能力提供了重要见解。

**Evaluating and Enhancing Spatial Cognition Abilities**（Yang et al., 2025）评估并增强了大语言模型的空间认知能力，提出了改进空间推理的方法。

### 2.4 场景图生成与空间理解

#### 2.4.1 场景图生成技术

场景图生成（SGG）旨在从图像中识别和提取对象并阐明其相互关系，是连接视觉感知和语义理解的关键技术。

**LLaVA-SpaceSGG**（Xu et al., 2025）提出了用于开放词汇场景图生成的多模态大语言模型，通过增强的空间关系建模，结合对象位置、对象关系和深度信息，在开放词汇SGG任务上取得了显著性能提升。

**MBRL方法**（Zhong et al., 2025）提出了处理语义歧义的混合平衡关系学习方法，为具有语义歧义的样本分配软标签，并通过调整细粒度和低频关系样本的损失权重来优化模型训练。

**DRSD方法**（Hu et al., 2024）提出了基于样本分布的动态重加权方法，根据训练过程中的样本分布计算类别权重，并引入对无关对象样本的重加权。

#### 2.4.2 多模态场景理解

**MAPE-ViT**（Ahmed et al., 2025）提出了多模态自适应补丁嵌入Vision Transformer，用于RGB-D场景分类，有效解决了传感器错位、深度噪声和对象边界保留等基本挑战。

**UrbanLLaVA**（Feng et al., 2025）是一个多模态大语言模型，用于城市智能的空间推理和理解，整合视觉和语言模态实现城市环境的深度理解。

### 2.5 智能体记忆与推理

#### 2.5.1 智能体记忆框架

**TiMem**（Li et al., 2026）提出了时间层次记忆整合框架，通过时间记忆树（TMT）组织对话，实现从原始对话观察到逐步抽象的人格表征的系统记忆整合。该框架具有三个核心特性：时间层次组织、语义引导整合和复杂度感知记忆召回。

#### 2.5.2 知识图谱与RAG

知识图谱和检索增强生成（RAG）技术为智能体提供了结构化的知识存储和检索能力。城市文本与知识图谱的结合可以支持复杂的空间推理和决策制定。

### 2.6 城市空间认知与行为分析

#### 2.6.1 城市情绪映射

Niu et al.（2025）使用地理标记的社交媒体数据调查城市环境中情感表达的空间分布，特别关注不同人群之间的差异。研究使用多模态深度学习模型推断用户的年龄和性别，识别不同人群的空间情绪模式。

#### 2.6.2 可达性与包容性

Li et al.（2025）通过众包在线评论研究公共无障碍性，使用Llama 3模型微调来识别公众对无障碍性的情感。研究发现大多数POI类别（餐馆、零售、酒店、医疗保健）显示负面情感，表明关键领域存在持续障碍。

### 2.7 城市规划与智能体应用

#### 2.7.1 城市规划智能体

**Towards Urban Planning AI Agent**（Liu et al., 2025）探讨了在智能体AI时代构建城市规划AI智能体的方向，为城市规划自动化提供了路线图。

**From Tools to Partners**（Pan et al., 2025）探讨了大语言模型如何转变城市规划，从工具角色向合作伙伴角色演进。

**Reimagining Urban Science**（Xia et al., 2025）提出了使用大语言模型扩展因果推断的城市科学新范式。

#### 2.7.2 交通与移动性

**Beyond Words**（Ying et al., 2024）评估了大语言模型在交通规划中的应用，识别了LLM在该领域的潜力和局限。

**UrbanLLM**（Jiang et al., 2024）提出了使用大语言模型进行自主城市活动规划和管理的方法。

#### 2.7.3 特殊领域应用

**UrbanMUDA**（Peng et al., 2025）提出了基于LLM智能体的城市军事单位部署选址方法，展示了智能体在特殊城市规划任务中的应用。

**Geo-hallucination in Urban Analytics**（Huang, 2025）研究了城市分析中的地理幻觉问题，对智能体系统的可靠性提出了重要警示。

### 2.8 城市信息模型（CIM）

城市信息模型（City Information Modeling, CIM）是数字孪生城市的重要基础。相关研究涉及：
- 基于NeRF的文物建筑数字化重建（程等，2023）
- 神经辐射场加速技术（郑，2023）
- 量化城市形态学（叶等，2021）
- 多源数据与深度学习支持下的人本城市设计（叶等，2021）

---

## 3. Research Gap

### 3.1 现有研究的局限性

通过对现有文献的系统分析，我们发现当前研究存在以下局限性：

#### 3.1.1 缺乏统一的城市分析智能体框架

现有研究大多针对特定城市任务（如能耗分析、制图、规划等）开发专门的智能体系统，缺乏能够统一处理多种城市任务的通用智能体框架。不同系统之间的工具、记忆和推理机制难以复用和迁移。

#### 3.1.2 多源数据融合能力不足

虽然已有研究探索了多模态数据融合（如STG4DUF），但现有LLM/VLM-based方法在处理异构城市数据（遥感、街景、OSM、GeoJSON、轨迹）的深度融合方面仍存在挑战。特别是如何将结构化地理数据与非结构化视觉、文本数据有效结合，仍需进一步研究。

#### 3.1.3 空间推理能力有限

CityBench和UrbanBench等基准测试表明，现有LLM/VLM在空间推理任务上表现不佳。特别是涉及复杂空间关系、拓扑结构、方向推理的任务，模型的准确性和鲁棒性有待提升。

#### 3.1.4 缺乏有效的记忆管理机制

城市分析任务通常涉及长时序、多尺度的信息处理，需要智能体具备有效的记忆管理能力。现有记忆框架（如TiMem）主要针对对话场景，对于城市空间分析中的时空记忆管理支持不足。

#### 3.1.5 工具集成和MCP应用不足

虽然MCP协议为智能体工具集成提供了标准化方案，但在城市分析领域的应用仍处于起步阶段。如何设计适合城市分析任务的工具集，并通过MCP实现高效集成，是亟待解决的问题。

### 3.2 本研究的创新点

针对上述研究空白，本研究提出以下创新点：

#### 3.2.1 统一的城市分析智能体框架

提出一个基于Agent框架的统一城市分析智能体系统，支持多种城市任务的协同处理。该框架将整合：
- **感知模块**：处理遥感影像、街景图像、OSM数据、GeoJSON、轨迹数据
- **推理模块**：基于场景图生成和知识图谱进行空间推理
- **决策模块**：支持城市规划、导航、交通控制等决策任务
- **记忆模块**：管理时空记忆，支持长时序分析

#### 3.2.2 多源数据深度融合机制

设计面向城市分析的多源数据融合机制：
- 将遥感影像和街景图像的视觉特征与OSM、GeoJSON的结构化特征对齐
- 利用轨迹数据增强空间动态理解
- 构建统一的城市空间表征（City Spatial Representation）

#### 3.2.3 增强的空间推理能力

通过以下方式提升智能体的空间推理能力：
- 集成场景图生成（SGG）技术，提取图像中的对象和关系
- 构建城市知识图谱，支持拓扑、方向、距离推理
- 设计空间推理专用工具，通过MCP协议集成

#### 3.2.4 时空记忆管理框架

设计适合城市分析的时空记忆管理框架：
- 支持多尺度（城市-街区-建筑）空间记忆
- 支持多时序（历史-当前-预测）时间记忆
- 实现记忆的层次化组织和高效检索

#### 3.2.5 基于CityBench的评估体系

基于CityBench的三维评估框架（状态感知、决策序列、任务结果），建立城市分析智能体的评估体系：
- 使用CityBench数据集进行测试
- 实现CityBench定义的核心指标
- 在8个城市任务上验证系统性能

---

## 4. 参考文献

### 城市分析Agent核心论文（32篇）

#### 基准测试与评估
1. Feng, J., Zhang, J., Liu, T., Zhang, X., Ouyang, T., Yan, J., Du, Y., Guo, S., Li, Y. (2024). CityBench: Evaluating the Capabilities of Large Language Models for Urban Tasks. *OpenReview*.
2. Zhao, X., Huang, H., Yang, T., Lu, Y., Zhang, L., Wang, R., Liu, Z., Zhong, T., Liu, T. (2025). Urban planning in the age of large language models: Assessing OpenAI o1's performance and capabilities across 556 tasks. *Computers, Environment and Urban Systems*, 121, 102332.
3. Lai, S., Ning, Y., Yuan, Z., Chen, Z., Liu, H. (2025). USTBench: Benchmarking and Dissecting Spatiotemporal Reasoning of LLMs as Urban Agents.
4. Zhang, Q., Gao, S., Wei, C., Zhao, Y., Nie, Y., Chen, Z., Chen, S., Su, Y., Sun, H. (2025). GeoAnalystBench: A GeoAI benchmark for assessing large language models for spatial analysis workflow and code generation.
5. Krechetova, V., Kochedykov, D. (2025). GeoBenchX: Benchmarking LLMs in Agent Solving Multistep Geospatial Tasks.

#### 多智能体系统
6. Quan, Y., Xiao, T., Gu, J., & Xu, P. (2025). AutoBEE: A hierarchical multi-agent approach for energy and environmental parameter analysis. *Energy and Buildings*, 349, 116516.
7. Wang, C., Kang, Y., Gong, Z., Zhao, P., Feng, Y., Zhang, W., Li, G. (2025). CartoAgent: a multimodal large language model-powered multi-agent cartographic framework for map style transfer and evaluation. *International Journal of Geographical Information Science*, 39(9), 1904-1937.
8. Yan, Y., Zeng, Q., Zheng, Z., Yuan, J., Feng, J., Zhang, J., Xu, F., Li, Y. (2024). OpenCity: A Scalable Platform to Simulate Urban Activities with Massive LLM Agents.
9. Kalyuzhnaya, A., Mityagin, S., Lutsenko, E., Getmanov, A., Aksenkin, Y., Fatkhiev, K., Fedorin, K., Nikitin, N.O., Chichkova, N., Vorona, V., Boukhanovsky, A. (2025). LLM Agents for Smart City Management: Enhancing Decision Support Through Multi-Agent AI Systems.
10. Lee, C., Paramanayakam, V., Karatzas, A., Jian, Y., Fore, M., Liao, H., Yu, F., Li, R., Anagnostopoulos, I., Stamoulis, D. (2025). Multi-Agent Geospatial Copilots for Remote Sensing Workflows.

#### 地理空间代码生成
11. Hou, S., Jiao, H., Liang, J., Shen, Z., Zhao, A., Wu, H. (2025). GeoCogent: an LLM-based agent for geospatial code generation.
12. Luo, Q., Lin, Q., Xu, L., Wu, S., Mao, R., Wang, C., Feng, H., Huang, B., Du, Z. (2025, 2026). GeoJSON agents: a multi-agent LLM architecture for geospatial analysis—function calling vs. code generation.
13. Lin, Q., Hu, R., Li, H., Wu, S., Li, Y., Fang, K., Feng, H., Du, Z., Xu, L. (2024). ShapefileGPT: A Multi-Agent Large Language Model Framework for Automated Shapefile Processing.
14. Chen, Y., Wang, W., Lobry, S., Kurtz, C. (2024). An LLM Agent for Automatic Geospatial Data Analysis.

#### 地图与空间推理
15. Hasan, M.H., Dihan, M.L., Hashem, T., Ali, M.E., Parvez, M.R. (2025). MapAgent: A Hierarchical Agent for Geospatial Reasoning with Dynamic Map Tool Integration.
16. Ananto, M.N.I., Fatin, S., Ali, M.E., Parvez, M.R. (2025). CompassLLM: A Multi-Agent Approach toward Geo-Spatial Reasoning for Popular Path Query.
17. Bao, R., Yang, C., Yu, D., Tang, Z., Mai, G., Zhao, L. (2026). Spatial-Agent: Agentic Geo-spatial Reasoning with Scientific Core Concepts.
18. Feng, J., Liu, T., Du, Y., Guo, S., Lin, Y., Li, Y. (2024). CityGPT: Empowering Urban Spatial Cognition of Large Language Models.

#### 空间认知与能力评估
19. Han, B., Wolfe, R., Caspi, A., Howe, B. (2025). Can Large Language Models Integrate Spatial Data? Empirical Insights into Reasoning Strengths and Computational Weaknesses.
20. Yang, A., Fu, C., Jia, Q., Dong, W., Ma, M., Chen, H., Yang, F., Wu, H. (2025). Evaluating and enhancing spatial cognition abilities of large language models.

#### 城市规划与应用
21. Liu, R., Zhe, T., Peng, Z.R., Catbas, N., Ye, X., Wang, D., Fu, Y. (2025). Towards Urban Planing AI Agent in the Age of Agentic AI.
22. Pan, F., Huang, X., Bi, Y., Gao, Y., Ye, Y., Wang, H. (2025). From tools to partners: How large language models are transforming urban planning.
23. Xia, Y., Qu, A., Zheng, Y., Tang, Y., Zhuang, D., Liang, Y., Wang, S., Wu, C., Sun, L., Zimmermann, R., Zhao, J. (2025). Reimagining Urban Science: Scaling Causal Inference with Large Language Models.
24. Ying, S., Li, Z., Yu, M. (2024). Beyond Words: Evaluating Large Language Models in Transportation Planning.
25. Jiang, Y., Chao, Q., Chen, Y., Li, X., Liu, S., Cong, G. (2024). UrbanLLM: Autonomous Urban Activity Planning and Management with Large Language Models.

#### 特殊领域应用
26. Peng, B., Wang, Y., Feng, C., Xia, X., Li, P. (2025). UrbanMUDA: an LLM Agent-based Site Selection Approach for Urban Military Unit Deployment.
27. Huang, X. (2025). Geo-hallucination in urban analytics: What it is and why it matters.

#### 多模态城市智能
28. Feng, J., Wang, S., Liu, T., Xi, Y., Li, Y. (2025). UrbanLLaVA: A Multi-modal Large Language Model for Urban Intelligence with Spatial Reasoning and Understanding.

### 多源感知与数据融合
29. Cao, J., Wang, X., Chen, G., Tu, W., Shen, X., Zhao, T., Chen, J., Li, Q. (2025). Disentangling the hourly dynamics of mixed urban function: A multimodal fusion perspective using dynamic graphs. *Information Fusion*, 117.
30. Kavee, K., & Flanigan, K. A. (2025). Encoding experience: Quantifying multisensory perception of urban form through a systematic review. *Computers, Environment and Urban Systems*, 122, 102349.
31. Yang, L., Luo, M., Zuo, Z., Kwan, M. P., Xi, D., Wan, B., Zhou, S. (2026). Deciphering the causes of getting lost in complex urban space: A multi-scale examination of spatial environmental indicators using multi-source data. *Applied Geography*, 186, 103854.

### 场景图生成
32. Xu, M., Wu, M., Zhao, Y., Li, J. C. L., Ou, W. (2025). LLaVA-SpaceSGG: Visual Instruct Tuning for Open-Vocabulary Scene Graph Generation with Enhanced Spatial Relations. *WACV*, 6362-6372.
33. Zhong, S., Cao, Y., Chen, Q., Gong, J. (2025). Learning with semantic ambiguity for unbiased scene graph generation. *PeerJ Computer Science*, 11.
34. Hu, L., Liu, S., & Wang, H. (2024). An Effective Dynamic Reweighting Method for Unbiased Scene Graph Generation. *Lecture Notes in Computer Science*, 14425, 345-356.
35. Sun, J., Zhang, Y., & Yang, X. (2023). A suggestion method for urban perception improvement using street-view images. *SPIE*, 12721.

### 智能体记忆
36. Li, K., Yu, X., Ni, Z., Zeng, Y., Xu, Y., Zhang, Z., Li, X., Sang, J., Duan, X., Wang, X., Liu, C., Tan, J. (2026). TiMem: Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents. *arXiv preprint* arXiv:2601.02845.

### 城市空间认知
37. Niu, H., Seraphim, A. P., Morgado, P., Miranda, B., & Silva, E. A. (2025). Mapping urban emotion from geotagged social media data: Age, gender and spatial heterogeneity. *Applied Geography*, 185, 103768.
38. Li, L., Hu, S., Dai, Y., Deng, M., Momeni, P., Laverghetta, G., Fan, L., Ma, Z., Wang, X., Ma, S., Ligatti, J., Hemphill, L. (2025). Toward satisfactory public accessibility: A crowdsourcing approach through online reviews to inclusive urban design. *Computers, Environment and Urban Systems*, 122, 102329.

### 城市信息模型
39. 叶宇, 黄鎔, 张灵珠. (2021). 量化城市形态学:涌现、概念及城市设计响应. *时代建筑*, (1), 34-43.
40. 叶宇, 黄鎔, 张灵珠. (2021). 多源数据与深度学习支持下的人本城市设计：以上海苏州河两岸城市绿道规划研究为例. *风景园林*, 28(1), 39-45.
41. 程斌, 杨勇, 徐崇斌, 李国帅, 任镤, 高致. (2023). 基于NeRF的文物建筑数字化重建. *航天返回与遥感*, 44(1), 40-49.

---

*文档更新时间: 2026-02-26*
*基于Zotero "城市分析agent"子分类32篇核心文献及相关研究整理*

# 城市分析智能体系统架构设计

## 1. 系统概述

### 1.1 设计目标

本系统旨在构建一个基于Agent框架的城市分析智能体，具备以下核心能力：
- **多源数据感知**：整合遥感影像、街景图像、OSM数据、GeoJSON、轨迹数据
- **空间推理能力**：基于场景图生成和知识图谱进行空间关系推理
- **任务执行能力**：支持CityBench 8个城市任务的执行
- **记忆管理能力**：支持时空记忆的存储、检索和推理
- **工具集成能力**：通过MCP协议集成各类城市分析工具

### 1.2 核心特性

1. **模块化设计**：各功能模块独立，便于扩展和维护
2. **多模态融合**：支持视觉、文本、结构化数据的统一处理
3. **可解释推理**：提供推理过程的可视化和解释
4. **可扩展工具**：支持通过MCP动态添加新工具
5. **评估对齐**：与CityBench三维评估框架对齐

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Urban Analysis Agent System                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   User      │  │  Planning   │  │   Memory    │  │  Evaluation │        │
│  │  Interface  │  │   Module    │  │   Module    │  │   Module    │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │               │
│         └────────────────┴────────────────┴────────────────┘               │
│                                   │                                         │
│                    ┌──────────────┴──────────────┐                         │
│                    │      Core Agent Engine      │                         │
│                    │  (LLM/VLM + Reasoning)      │                         │
│                    └──────────────┬──────────────┘                         │
│                                   │                                         │
│         ┌─────────────────────────┼─────────────────────────┐              │
│         │                         │                         │              │
│  ┌──────┴──────┐         ┌────────┴────────┐       ┌───────┴──────┐       │
│  │  Perception │         │   Reasoning     │       │   Action     │       │
│  │   Module    │         │    Module       │       │   Module     │       │
│  └──────┬──────┘         └────────┬────────┘       └───────┬──────┘       │
│         │                         │                         │              │
│  ┌──────┴──────┐         ┌────────┴────────┐       ┌───────┴──────┐       │
│  │• Remote     │         │• Scene Graph    │       │• MCP Tools   │       │
│  │  Sensing    │         │  Generation     │       │• API Calls   │       │
│  │• StreetView │         │• Knowledge      │       │• Data Output │       │
│  │• OSM Data   │         │  Graph          │       │              │       │
│  │• GeoJSON    │         │• Spatial        │       │              │       │
│  │• Trajectory │         │  Reasoning      │       │              │       │
│  └─────────────┘         └─────────────────┘       └──────────────┘       │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块详细设计

#### 2.2.1 感知模块 (Perception Module)

**功能**：处理多源城市数据，提取特征并统一表征

**子模块**：

1. **遥感影像处理器 (RemoteSensingProcessor)**
   ```python
   class RemoteSensingProcessor:
       """处理遥感影像数据"""
       
       def process_image(self, image_path: str) -> Dict:
           """
           处理遥感影像
           - 图像预处理（裁剪、归一化）
           - 特征提取（使用预训练VLM）
           - 场景分类（人口密度、基础设施等）
           """
           pass
       
       def extract_objects(self, image_path: str) -> List[Dict]:
           """
           提取遥感影像中的对象
           - 建筑物检测
           - 道路提取
           - 绿地识别
           """
           pass
   ```

2. **街景图像处理器 (StreetViewProcessor)**
   ```python
   class StreetViewProcessor:
       """处理街景图像数据"""
       
       def analyze_perception(self, image_path: str) -> Dict:
           """
           分析街景感知属性
           - 美观度 (Beautiful)
           - 安全性 (Safe)
           - 富裕度 (Wealthy)
           - 活力度 (Lively)
           - 无聊度 (Boring)
           - 压抑度 (Depressing)
           """
           pass
       
       def generate_scene_graph(self, image_path: str) -> Dict:
           """
           生成场景图
           - 对象检测
           - 关系识别
           - 空间关系建模
           """
           pass
       
       def geolocate(self, image_path: str) -> Dict:
           """
           街景地理定位
           - 视觉地标识别
           - 城市特征匹配
           - 候选城市重排
           """
           pass
   ```

3. **OSM数据处理器 (OSMProcessor)**
   ```python
   class OSMProcessor:
       """处理OpenStreetMap数据"""
       
       def parse_osm(self, osm_data: Union[str, Dict]) -> Dict:
           """
           解析OSM数据
           - 节点提取
           - 道路网络构建
           - POI识别
           """
           pass
       
       def build_graph(self, osm_data: Dict) -> nx.Graph:
           """
           构建路网图
           - 节点和边创建
           - 属性赋值
           - 拓扑关系建立
           """
           pass
       
       def extract_features(self, osm_data: Dict) -> Dict:
           """
           提取OSM特征
           - 道路类型分布
           - 建筑密度
           - 设施分布
           """
           pass
   ```

4. **GeoJSON处理器 (GeoJSONProcessor)**
   ```python
   class GeoJSONProcessor:
       """处理GeoJSON矢量数据"""
       
       def parse_geojson(self, geojson_data: Union[str, Dict]) -> gpd.GeoDataFrame:
           """
           解析GeoJSON数据
           - 几何对象提取
           - 属性表构建
           - 空间索引创建
           """
           pass
       
       def spatial_analysis(self, gdf: gpd.GeoDataFrame) -> Dict:
           """
           空间分析
           - 面积计算
           - 缓冲区分析
           - 叠加分析
           """
           pass
   ```

5. **轨迹数据处理器 (TrajectoryProcessor)**
   ```python
   class TrajectoryProcessor:
       """处理轨迹数据"""
       
       def parse_trajectory(self, trajectory_data: List[Dict]) -> pd.DataFrame:
           """
           解析轨迹数据
           - 时间序列处理
           - 空间点序列提取
           - 速度计算
           """
           pass
       
       def analyze_mobility_patterns(self, df: pd.DataFrame) -> Dict:
           """
           分析移动模式
           - 停留点检测
           - 移动路径聚类
           - 时间规律挖掘
           """
           pass
       
       def predict_next_location(self, df: pd.DataFrame, context: Dict) -> Dict:
           """
           预测下一个位置
           - 历史模式匹配
           - 上下文感知
           - Top-k预测
           """
           pass
   ```

#### 2.2.2 推理模块 (Reasoning Module)

**功能**：基于感知结果进行空间推理和决策

**子模块**：

1. **场景图生成器 (SceneGraphGenerator)**
   ```python
   class SceneGraphGenerator:
       """生成图像的场景图表示"""
       
       def __init__(self, model_name: str = "LLaVA-SpaceSGG"):
           self.model = self._load_model(model_name)
       
       def generate(self, image_path: str) -> SceneGraph:
           """
           生成场景图
           Returns:
               SceneGraph: 包含对象、关系和属性的图结构
           """
           # 1. 对象检测
           objects = self._detect_objects(image_path)
           # 2. 关系识别
           relations = self._detect_relations(image_path, objects)
           # 3. 属性提取
           attributes = self._extract_attributes(image_path, objects)
           # 4. 构建图
           return SceneGraph(objects, relations, attributes)
       
       def to_text(self, scene_graph: SceneGraph) -> str:
           """将场景图转换为文本描述"""
           pass
   ```

2. **知识图谱推理器 (KnowledgeGraphReasoner)**
   ```python
   class KnowledgeGraphReasoner:
       """基于知识图谱的空间推理"""
       
       def __init__(self, kg_path: Optional[str] = None):
           self.kg = self._load_or_build_kg(kg_path)
       
       def spatial_reasoning(self, query: str, context: Dict) -> Dict:
           """
           空间推理
           - 拓扑关系推理（相交、包含、相邻）
           - 方向关系推理（东、南、西、北）
           - 距离关系推理（近、远）
           """
           pass
       
       def multi_hop_reasoning(self, query: str, max_hops: int = 3) -> Dict:
           """
           多跳推理
           - 路径搜索
           - 关系链推理
           - 答案聚合
           """
           pass
       
       def query(self, sparql_query: str) -> List[Dict]:
           """执行SPARQL查询"""
           pass
   ```

3. **空间推理引擎 (SpatialReasoningEngine)**
   ```python
   class SpatialReasoningEngine:
       """空间推理引擎"""
       
       def __init__(self):
           self.scene_graph_generator = SceneGraphGenerator()
           self.kg_reasoner = KnowledgeGraphReasoner()
       
       def reason(self, query: str, data_context: Dict) -> ReasoningResult:
           """
           执行空间推理
           
           Args:
               query: 查询问题
               data_context: 数据上下文（图像、地图、轨迹等）
           
           Returns:
               ReasoningResult: 包含推理结果和解释
           """
           # 1. 数据预处理
           processed_data = self._preprocess(data_context)
           
           # 2. 场景图生成（如果有图像）
           if 'image' in processed_data:
               scene_graph = self.scene_graph_generator.generate(
                   processed_data['image']
               )
               processed_data['scene_graph'] = scene_graph
           
           # 3. 知识图谱查询
           kg_results = self.kg_reasoner.spatial_reasoning(
               query, processed_data
           )
           
           # 4. LLM推理
           llm_result = self._llm_reason(query, processed_data, kg_results)
           
           # 5. 结果整合
           return self._integrate_results(llm_result, kg_results)
   ```

#### 2.2.3 记忆模块 (Memory Module)

**功能**：管理智能体的时空记忆

**设计**：

```python
class SpatiotemporalMemory:
    """时空记忆管理器"""
    
    def __init__(self):
        # 短期记忆：当前会话
        self.short_term = ShortTermMemory()
        # 工作记忆：当前任务上下文
        self.working = WorkingMemory()
        # 长期记忆：历史知识和经验
        self.long_term = LongTermMemory()
        # 空间记忆：地理空间信息
        self.spatial = SpatialMemory()
    
    def store(self, memory_item: MemoryItem) -> str:
        """
        存储记忆项
        
        Args:
            memory_item: 包含内容、时间、空间位置的记忆项
        
        Returns:
            memory_id: 记忆唯一标识
        """
        # 根据类型存储到相应记忆区
        if memory_item.is_temporal():
            return self._store_temporal(memory_item)
        elif memory_item.is_spatial():
            return self._store_spatial(memory_item)
        else:
            return self._store_general(memory_item)
    
    def retrieve(self, query: str, filters: Dict = None) -> List[MemoryItem]:
        """
        检索记忆
        
        Args:
            query: 查询内容
            filters: 过滤条件（时间范围、空间范围等）
        
        Returns:
            List[MemoryItem]: 匹配的记忆项列表
        """
        # 多层级检索
        results = []
        results.extend(self.short_term.search(query))
        results.extend(self.working.search(query))
        results.extend(self.long_term.search(query, filters))
        results.extend(self.spatial.search(query, filters))
        
        # 排序和过滤
        return self._rank_and_filter(results, query)
    
    def consolidate(self):
        """记忆整合：将短期记忆转移到长期记忆"""
        items = self.short_term.get_consolidation_candidates()
        for item in items:
            self.long_term.store(item)
        self.short_term.clear_consolidated()


class SpatialMemory:
    """空间记忆：存储和检索地理空间信息"""
    
    def __init__(self):
        # 使用R-tree空间索引
        self.spatial_index = RTreeIndex()
        # 空间实体存储
        self.entities = {}
    
    def store_entity(self, entity_id: str, geometry: Dict, 
                     attributes: Dict) -> str:
        """存储空间实体"""
        # 创建空间索引条目
        bbox = self._get_bbox(geometry)
        self.spatial_index.insert(entity_id, bbox)
        
        # 存储实体数据
        self.entities[entity_id] = {
            'geometry': geometry,
            'attributes': attributes,
            'timestamp': datetime.now()
        }
        
        return entity_id
    
    def spatial_query(self, query_geometry: Dict, 
                      predicate: str = 'intersects') -> List[Dict]:
        """
        空间查询
        
        Args:
            query_geometry: 查询几何
            predicate: 空间谓词（intersects, contains, within等）
        
        Returns:
            List[Dict]: 匹配的空间实体
        """
        # 使用R-tree进行初步过滤
        candidates = self.spatial_index.intersection(
            self._get_bbox(query_geometry)
        )
        
        # 精确几何计算
        results = []
        for entity_id in candidates:
            entity = self.entities[entity_id]
            if self._spatial_predicate(
                query_geometry, entity['geometry'], predicate
            ):
                results.append(entity)
        
        return results
```

#### 2.2.4 规划模块 (Planning Module)

**功能**：任务分解和规划

```python
class TaskPlanner:
    """任务规划器"""
    
    def __init__(self):
        self.llm = LLMClient()
    
    def plan(self, task: str, context: Dict) -> ExecutionPlan:
        """
        制定执行计划
        
        Args:
            task: 任务描述
            context: 任务上下文
        
        Returns:
            ExecutionPlan: 执行计划
        """
        # 1. 任务分解
        subtasks = self._decompose_task(task, context)
        
        # 2. 依赖分析
        dependencies = self._analyze_dependencies(subtasks)
        
        # 3. 工具选择
        tool_assignments = self._assign_tools(subtasks)
        
        # 4. 构建执行图
        return ExecutionPlan(
            subtasks=subtasks,
            dependencies=dependencies,
            tool_assignments=tool_assignments
        )
    
    def _decompose_task(self, task: str, context: Dict) -> List[SubTask]:
        """
        将任务分解为子任务
        
        示例：
        任务："分析该区域的人口密度分布"
        子任务：
        1. 加载遥感影像
        2. 提取建筑区域
        3. 估算人口密度
        4. 生成分布图
        """
        prompt = f"""
        将以下城市分析任务分解为具体的子任务：
        
        任务：{task}
        上下文：{context}
        
        请输出子任务列表，每个子任务包含：
        - 任务ID
        - 任务描述
        - 所需输入
        - 预期输出
        - 依赖的前置任务
        """
        
        response = self.llm.generate(prompt)
        return self._parse_subtasks(response)


class ExecutionPlan:
    """执行计划"""
    
    def __init__(self, subtasks: List[SubTask], 
                 dependencies: Dict[str, List[str]],
                 tool_assignments: Dict[str, str]):
        self.subtasks = subtasks
        self.dependencies = dependencies
        self.tool_assignments = tool_assignments
        self.execution_graph = self._build_graph()
    
    def execute(self, executor: 'AgentExecutor') -> ExecutionResult:
        """执行计划"""
        results = {}
        
        # 拓扑排序，按依赖顺序执行
        execution_order = self._topological_sort()
        
        for task_id in execution_order:
            subtask = self._get_subtask(task_id)
            tool = self.tool_assignments.get(task_id)
            
            # 准备输入（从前置任务获取结果）
            inputs = self._prepare_inputs(task_id, results)
            
            # 执行子任务
            result = executor.execute_subtask(subtask, tool, inputs)
            results[task_id] = result
        
        return ExecutionResult(results)
```

#### 2.2.5 行动模块 (Action Module)

**功能**：执行具体行动，通过MCP协议调用工具

```python
class ActionModule:
    """行动执行模块"""
    
    def __init__(self):
        self.mcp_client = MCPClient()
        self.tool_registry = ToolRegistry()
    
    def execute(self, action: Action) -> ActionResult:
        """
        执行行动
        
        Args:
            action: 行动定义（工具名称、参数等）
        
        Returns:
            ActionResult: 执行结果
        """
        tool_name = action.tool_name
        parameters = action.parameters
        
        # 通过MCP调用工具
        if self.tool_registry.is_mcp_tool(tool_name):
            return self.mcp_client.call(tool_name, parameters)
        else:
            # 本地工具执行
            tool = self.tool_registry.get_tool(tool_name)
            return tool.execute(**parameters)


class MCPClient:
    """MCP协议客户端"""
    
    def __init__(self):
        self.servers = {}
    
    def register_server(self, server_name: str, 
                        server_config: Dict):
        """注册MCP服务器"""
        self.servers[server_name] = MCPConnection(server_config)
    
    def call(self, tool_name: str, parameters: Dict) -> Dict:
        """调用MCP工具"""
        # 查找工具所在的服务器
        server = self._find_tool_server(tool_name)
        
        # 构建MCP请求
        request = {
            "jsonrpc": "2.0",
            "method": tool_name,
            "params": parameters,
            "id": self._generate_id()
        }
        
        # 发送请求并获取响应
        response = server.send_request(request)
        return response["result"]
```

#### 2.2.6 评估模块 (Evaluation Module)

**功能**：基于CityBench三维评估框架进行系统评估

```python
class CityBenchEvaluator:
    """CityBench评估器"""
    
    def __init__(self):
        self.metrics = {
            'state_perception': StatePerceptionMetrics(),
            'decision_sequence': DecisionSequenceMetrics(),
            'task_outcome': TaskOutcomeMetrics()
        }
    
    def evaluate(self, task_name: str, 
                 predictions: List[Dict],
                 ground_truth: List[Dict]) -> EvaluationReport:
        """
        评估任务执行结果
        
        Args:
            task_name: 任务名称（traffic, navigation, geoqa等）
            predictions: 模型预测结果
            ground_truth: 真实标签
        
        Returns:
            EvaluationReport: 评估报告
        """
        results = {}
        
        # 1. 状态感知评估
        results['state_perception'] = self.metrics['state_perception'].compute(
            task_name, predictions, ground_truth
        )
        
        # 2. 决策序列评估
        results['decision_sequence'] = self.metrics['decision_sequence'].compute(
            task_name, predictions, ground_truth
        )
        
        # 3. 任务结果评估
        results['task_outcome'] = self.metrics['task_outcome'].compute(
            task_name, predictions, ground_truth
        )
        
        return EvaluationReport(results)


class StatePerceptionMetrics:
    """状态感知指标"""
    
    def compute(self, task_name: str, predictions: List[Dict], 
                ground_truth: List[Dict]) -> Dict:
        """
        计算状态感知指标
        
        不同任务的指标：
        - traffic: 路口相位识别准确率、队列长度估计误差
        - exploration: 当前位置与目标相对关系识别、可达性判断准确率
        - navigation: 邻接路段识别、方向感知准确率、地标-路径一致性
        - mobility: 用户历史停留模式感知、时间上下文理解
        - geoqa: 空间关系识别准确率、地理常识命中率
        - population: 图像场景与人口密度相关特征感知
        - objects: 基础设施目标识别准确率
        - geoloc: 视觉地标感知、城市特征匹配
        """
        metrics = {}
        
        if task_name == 'traffic':
            metrics['phase_accuracy'] = self._compute_phase_accuracy(
                predictions, ground_truth
            )
            metrics['queue_length_error'] = self._compute_queue_length_error(
                predictions, ground_truth
            )
        
        elif task_name == 'navigation':
            metrics['adjacent_road_accuracy'] = self._compute_adjacent_road_accuracy(
                predictions, ground_truth
            )
            metrics['direction_accuracy'] = self._compute_direction_accuracy(
                predictions, ground_truth
            )
        
        # ... 其他任务的指标计算
        
        return metrics


class DecisionSequenceMetrics:
    """决策序列指标"""
    
    def compute(self, task_name: str, predictions: List[Dict],
                ground_truth: List[Dict]) -> Dict:
        """
        计算决策序列指标
        
        不同任务的指标：
        - traffic: 动作合法率、冲突动作率、时序稳定性
        - exploration: 成功轨迹率、平均决策步数、无效动作率
        - navigation: 路径执行成功率、回退/震荡率、平均决策轮数
        - mobility: 多轮候选更新质量、Top-k收敛稳定性
        - geoqa: 多跳推理一致率
        - geoloc: 候选城市重排稳定性
        """
        metrics = {}
        
        if task_name == 'traffic':
            metrics['action_validity'] = self._compute_action_validity(
                predictions, ground_truth
            )
            metrics['conflict_rate'] = self._compute_conflict_rate(
                predictions, ground_truth
            )
        
        elif task_name == 'exploration':
            metrics['success_trajectory_rate'] = self._compute_success_trajectory_rate(
                predictions, ground_truth
            )
            metrics['avg_decision_steps'] = self._compute_avg_decision_steps(
                predictions, ground_truth
            )
        
        # ... 其他任务的指标计算
        
        return metrics


class TaskOutcomeMetrics:
    """任务结果指标"""
    
    def compute(self, task_name: str, predictions: List[Dict],
                ground_truth: List[Dict]) -> Dict:
        """
        计算任务结果指标（CityBench主指标）
        
        不同任务的指标：
        - traffic: Average_Queue_Length, Throughput
        - exploration: Exploration_Success_Ratio, Exploration_Average_Steps
        - navigation: Navigation_Success_Ratio, Navigation_Average_Distance
        - mobility: Acc@1, F1
        - geoqa: GeoQA_Average_Accuracy
        - population: RMSE, r2
        - objects: Infrastructure_Accuracy
        - geoloc: City_Accuracy, Acc@25km
        """
        metrics = {}
        
        if task_name == 'traffic':
            metrics['avg_queue_length'] = self._compute_avg_queue_length(
                predictions, ground_truth
            )
            metrics['throughput'] = self._compute_throughput(
                predictions, ground_truth
            )
        
        elif task_name == 'geoqa':
            metrics['accuracy'] = self._compute_accuracy(
                predictions, ground_truth
            )
        
        elif task_name == 'population':
            metrics['rmse'] = self._compute_rmse(
                predictions, ground_truth
            )
            metrics['r2'] = self._compute_r2(
                predictions, ground_truth
            )
        
        # ... 其他任务的指标计算
        
        return metrics
```

---

## 3. 数据流设计

### 3.1 典型任务数据流

#### 3.1.1 交通控制任务 (Traffic)

```
用户输入: "优化该路口的交通信号控制"
    ↓
[Planning Module] 任务分解
    - 加载路口拓扑结构
    - 获取当前交通状态
    - 预测交通流量
    - 生成信号控制策略
    ↓
[Perception Module] 状态感知
    - OSMProcessor: 提取路口拓扑
    - TrajectoryProcessor: 分析车辆轨迹
    - 计算队列长度、车流量
    ↓
[Reasoning Module] 决策推理
    - SpatialReasoningEngine: 分析交通模式
    - 生成相位控制决策
    ↓
[Action Module] 执行行动
    - 输出信号控制方案
    ↓
[Evaluation Module] 结果评估
    - 计算Average_Queue_Length
    - 计算Throughput
```

#### 3.1.2 地理问答任务 (GeoQA)

```
用户输入: "北京故宫的北侧是什么建筑？"
    ↓
[Planning Module] 任务分解
    - 解析问题实体（北京故宫）
    - 确定空间关系（北侧）
    - 检索相关知识
    - 生成答案
    ↓
[Perception Module] 知识检索
    - KnowledgeGraphReasoner: 查询知识图谱
    - 获取故宫及其周边建筑信息
    ↓
[Reasoning Module] 空间推理
    - 多跳推理：故宫 → 地理位置 → 北侧建筑
    - 验证空间关系
    ↓
[Action Module] 生成答案
    - 输出: "景山公园"
    ↓
[Evaluation Module] 结果评估
    - 计算GeoQA_Average_Accuracy
```

#### 3.1.3 人口估计任务 (Population)

```
用户输入: "估计这张遥感影像区域的人口密度"
    ↓
[Planning Module] 任务分解
    - 加载遥感影像
    - 提取建筑特征
    - 估算人口密度
    - 输出结果
    ↓
[Perception Module] 图像分析
    - RemoteSensingProcessor: 处理影像
    - extract_objects: 检测建筑物
    - 提取建筑密度、高度等特征
    ↓
[Reasoning Module] 密度推理
    - 基于建筑特征估算人口
    - 结合区域类型调整
    ↓
[Action Module] 输出结果
    - 输出人口密度估计值
    ↓
[Evaluation Module] 结果评估
    - 计算RMSE
    - 计算r2
```

---

## 4. MCP工具设计

### 4.1 工具分类

```python
# 感知类工具
PERCEPTION_TOOLS = {
    "remote_sensing.analyze": {
        "description": "分析遥感影像",
        "parameters": {
            "image_path": "影像路径",
            "analysis_type": "分析类型（population/objects/land_use）"
        }
    },
    "street_view.analyze": {
        "description": "分析街景图像",
        "parameters": {
            "image_path": "图像路径",
            "analysis_type": "分析类型（perception/scene_graph/geoloc）"
        }
    },
    "osm.parse": {
        "description": "解析OSM数据",
        "parameters": {
            "osm_data": "OSM数据（文件路径或数据字典）",
            "extract_type": "提取类型（roads/buildings/pois）"
        }
    },
    "geojson.parse": {
        "description": "解析GeoJSON数据",
        "parameters": {
            "geojson_data": "GeoJSON数据",
            "operation": "操作类型（parse/analyze）"
        }
    },
    "trajectory.analyze": {
        "description": "分析轨迹数据",
        "parameters": {
            "trajectory_data": "轨迹数据",
            "analysis_type": "分析类型（patterns/prediction）"
        }
    }
}

# 推理类工具
REASONING_TOOLS = {
    "scene_graph.generate": {
        "description": "生成场景图",
        "parameters": {
            "image_path": "图像路径",
            "output_format": "输出格式（graph/text）"
        }
    },
    "spatial_reasoning.query": {
        "description": "空间推理查询",
        "parameters": {
            "query": "查询问题",
            "context": "上下文信息"
        }
    },
    "knowledge_graph.query": {
        "description": "知识图谱查询",
        "parameters": {
            "sparql_query": "SPARQL查询语句",
            "query_type": "查询类型"
        }
    }
}

# 行动类工具
ACTION_TOOLS = {
    "navigation.plan": {
        "description": "规划导航路径",
        "parameters": {
            "start": "起点",
            "destination": "终点",
            "constraints": "约束条件"
        }
    },
    "traffic.control": {
        "description": "生成交通控制策略",
        "parameters": {
            "intersection_id": "路口ID",
            "traffic_state": "交通状态",
            "optimization_goal": "优化目标"
        }
    }
}
```

### 4.2 MCP服务器配置

```json
{
  "mcpServers": {
    "urban_perception": {
      "command": "python",
      "args": ["-m", "urban_agent.mcp.perception_server"],
      "env": {
        "DATA_ROOT": "./data"
      }
    },
    "urban_reasoning": {
      "command": "python",
      "args": ["-m", "urban_agent.mcp.reasoning_server"],
      "env": {
        "KG_PATH": "./data/knowledge_graph.ttl"
      }
    },
    "urban_action": {
      "command": "python",
      "args": ["-m", "urban_agent.mcp.action_server"],
      "env": {}
    }
  }
}
```

---

## 5. 接口设计

### 5.1 核心类接口

```python
# 主Agent类
class UrbanAnalysisAgent:
    """城市分析智能体主类"""
    
    def __init__(self, config: AgentConfig):
        """
        初始化智能体
        
        Args:
            config: 智能体配置
        """
        self.perception = PerceptionModule()
        self.reasoning = ReasoningModule()
        self.memory = SpatiotemporalMemory()
        self.planning = TaskPlanner()
        self.action = ActionModule()
        self.evaluation = CityBenchEvaluator()
    
    def analyze(self, task: str, data_sources: Dict) -> AnalysisResult:
        """
        执行城市分析任务
        
        Args:
            task: 任务描述
            data_sources: 数据源配置
        
        Returns:
            AnalysisResult: 分析结果
        """
        # 1. 任务规划
        plan = self.planning.plan(task, data_sources)
        
        # 2. 数据感知
        perceived_data = self.perception.process(data_sources)
        
        # 3. 存储到记忆
        self.memory.store(perceived_data)
        
        # 4. 推理分析
        reasoning_result = self.reasoning.reason(task, perceived_data)
        
        # 5. 执行行动
        action_result = self.action.execute(plan, reasoning_result)
        
        # 6. 结果评估
        evaluation = self.evaluation.evaluate(task, action_result)
        
        return AnalysisResult(
            reasoning=reasoning_result,
            action=action_result,
            evaluation=evaluation
        )
    
    def chat(self, message: str, context: Dict = None) -> str:
        """
        对话接口
        
        Args:
            message: 用户消息
            context: 对话上下文
        
        Returns:
            str: 回复消息
        """
        # 检索相关记忆
        relevant_memories = self.memory.retrieve(message)
        
        # 构建提示
        prompt = self._build_chat_prompt(message, relevant_memories, context)
        
        # 生成回复
        response = self.llm.generate(prompt)
        
        # 存储对话
        self.memory.store_conversation(message, response)
        
        return response


# 配置类
@dataclass
class AgentConfig:
    """智能体配置"""
    llm_model: str = "gpt-4"
    vlm_model: str = "gpt-4-vision"
    memory_config: MemoryConfig = field(default_factory=MemoryConfig)
    mcp_servers: List[str] = field(default_factory=list)
    tool_paths: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """分析结果"""
    reasoning: Dict
    action: Dict
    evaluation: Dict
    execution_time: float
    metadata: Dict
```

### 5.2 REST API接口

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()
agent = UrbanAnalysisAgent(config=AgentConfig())

class AnalyzeRequest(BaseModel):
    task: str
    data_sources: Dict
    parameters: Optional[Dict] = None

class AnalyzeResponse(BaseModel):
    result: Dict
    evaluation: Dict
    execution_time: float

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """执行城市分析任务"""
    result = agent.analyze(request.task, request.data_sources)
    return AnalyzeResponse(
        result=result.reasoning,
        evaluation=result.evaluation,
        execution_time=result.execution_time
    )

@app.post("/chat")
async def chat(message: str, session_id: Optional[str] = None):
    """对话接口"""
    context = {"session_id": session_id} if session_id else {}
    response = agent.chat(message, context)
    return {"response": response}

@app.get("/tasks")
async def list_tasks():
    """列出支持的任务类型"""
    return {
        "tasks": [
            "traffic",
            "exploration",
            "navigation",
            "mobility",
            "geoqa",
            "population",
            "objects",
            "geoloc"
        ]
    }
```

---

## 6. 部署架构

### 6.1 组件部署图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Web UI    │  │   CLI Tool  │  │   API Client│             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
└─────────┼────────────────┼────────────────┼────────────────────┘
          │                │                │
          └────────────────┴────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    API Gateway Layer                             │
│              (FastAPI / Flask REST API)                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    Core Agent Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Perception │  │   Reasoning │  │    Memory   │             │
│  │   Module    │  │    Module   │  │    Module   │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┴────────────────┘                     │
│                           │                                      │
│                    ┌──────┴──────┐                              │
│                    │  LLM/VLM    │                              │
│                    │  (OpenAI/   │                              │
│                    │  Local)     │                              │
│                    └─────────────┘                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    MCP Tool Layer                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Perception  │  │  Reasoning  │  │   Action    │             │
│  │   Server    │  │   Server    │  │   Server    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    Data Layer                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  CityBench  │  │   OSM Data  │  │   Vector    │             │
│  │    Data     │  │             │  │    Data     │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Remote    │  │   Street    │  │  Knowledge  │             │
│  │   Sensing   │  │    View     │  │    Graph    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 配置文件

```yaml
# config.yaml
agent:
  name: "UrbanAnalysisAgent"
  version: "1.0.0"
  
llm:
  provider: "openai"
  model: "gpt-4"
  api_key: "${OPENAI_API_KEY}"
  temperature: 0.7
  max_tokens: 2000

vlm:
  provider: "openai"
  model: "gpt-4-vision-preview"
  api_key: "${OPENAI_API_KEY}"

memory:
  type: "hybrid"
  short_term:
    max_items: 100
  long_term:
    vector_store: "chroma"
    embedding_model: "text-embedding-3-small"
  spatial:
    index_type: "rtree"

mcp:
  servers:
    - name: "urban_perception"
      command: "python -m urban_agent.mcp.perception_server"
    - name: "urban_reasoning"
      command: "python -m urban_agent.mcp.reasoning_server"
    - name: "urban_action"
      command: "python -m urban_agent.mcp.action_server"

evaluation:
  citybench_data_path: "./third_party/CityBench-main/data"
  metrics:
    - state_perception
    - decision_sequence
    - task_outcome

data:
  remote_sensing:
    path: "./data/remote_sensing"
  street_view:
    path: "./data/street_view"
  osm:
    path: "./data/osm"
  trajectory:
    path: "./data/trajectory"
  knowledge_graph:
    path: "./data/knowledge_graph.ttl"
```

---

## 7. 总结

本文档设计了城市分析智能体系统的完整架构，包括：

1. **感知模块**：支持遥感影像、街景图像、OSM、GeoJSON、轨迹数据的多源数据处理
2. **推理模块**：基于场景图生成和知识图谱的空间推理能力
3. **记忆模块**：时空记忆管理，支持多尺度、多时序信息存储和检索
4. **规划模块**：任务分解和执行计划生成
5. **行动模块**：通过MCP协议集成各类城市分析工具
6. **评估模块**：基于CityBench三维评估框架的系统评估

该架构设计遵循模块化、可扩展、可评估的原则，为后续的系统实现和测试奠定了基础。

---

*文档生成时间: 2026-02-26*

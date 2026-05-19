# Case 2 测试包：街景感知与城市 Outcome 对齐分析

> **角色说明：** 你（或你的本地 agent）是测试者+撰写者。Urban-Hermes 是受测的城市空间智能体。
> 你的任务是按本文档操作 Urban-Hermes CLI，收集每一轮对话 transcript 和产物，
> 然后把这些证据写成论文第五章的 5.4 节（流程导向的 Case 2 实验）。
>
> **核心论证目标：** 你在 5.4 里要证明的不是“模型答对了”，而是：
> - **Gap 1（输入锚定）**：Urban-Hermes 能把一句自然语言研究意图变成可检查的数据边界、指标证据要求、direct/proxy/missing 分类
> - **Gap 2（推理可验证）**：Urban-Hermes 的中间推理能转化为外部可读的空间产物（GeoJSON、CSV、QGIS 工程），失败能被 reviewer 和独立 validator 抓到并纠正
>
> ——以上是 5.4 的核心。Gap 3（跨任务记忆复用）留给 5.5。

> **2026-05-19 更新：** 正式给合作者复跑时，优先使用 `COLLABORATOR_REALISTIC_TEST_README.md` 和 `prompts/case2_realistic_research_dialogue_script.md`。旧的 `case2_full_prompt.md` 太完整，适合作 smoke test 或对照，不适合作 5.4 主实验的真实人机对话证据。

---

## 0. 包内文件清单

```
case2_tester_package/
├── CASE2_TESTER_HANDBOOK.md          ← 你正在读的这个文件
├── AGENT_TESTER_OPERATOR_GUIDE.md    ← 给 OpenClaw/Claude Code 等外部 agent 的测试员操作规约
├── COLLABORATOR_REALISTIC_TEST_README.md ← 合作者入口：真实对话版测试说明
├── INSTALL_LATEST_URBAN_HERMES.md    ← 最新 Urban-Hermes 安装与冒烟验收清单
├── KIMI_CODE_API_SETUP.md            ← Kimi Code API key 配置短指南
├── prompts/
│   ├── case2_realistic_research_dialogue_script.md ← 正式推荐：低结构真实对话脚本
│   ├── case2_natural_question_sequence.md ← 早期自然问题序列，保留作基线
│   ├── case2_full_prompt.md          ← 合并式完整 prompt，仅用于 smoke test/对照
│   ├── case2_correction_feedback.md  ← 测试者纠正 prompt
│   ├── case2_round2_prompt.md        ← 纠正后第二轮 prompt
│   ├── realistic_dialogue/            ← 可逐轮读取的短 prompt
│   │   ├── turn1_scoping.md
│   │   ├── turn2a_design_3d5d.md
│   │   ├── turn2b_execute_3d5d.md
│   │   ├── turn3_gwr_gwrf_review.md
│   │   └── turn4_perception_extension.md
│   └── ablation/
│       ├── a1_no_urban_toolset.md     ← 消融 A1
│       ├── a2_no_ground_review.md     ← 消融 A2
│       └── a3_no_memory.md            ← 消融 A3
├── env/
│   └── kimi_code.env.example          ← Kimi Code API key 模板，不含真实密钥
├── scripts/
│   └── load_kimi_code_env.ps1         ← 本地加载 Kimi Code 环境变量
├── data_canvas/
│   ├── README.md                     ← 数据画布说明：需要准备什么文件
│   └── sample_metadata.json          ← 元数据模板
├── qgis_validation/
│   └── validate_case_qgis.py         ← 独立 QGIS 验收脚本
├── evaluation_templates/
│   ├── tester_evaluation_template.md ← 每轮测试员评估记录模板
│   ├── realistic_turn_evaluation_template.md ← 真实对话版逐轮评价模板
│   ├── collaborator_return_manifest_template.md ← 合作者回传材料清单模板
│   ├── section_5_4_writing_guide.md  ← 5.4 节撰写指南
│   └── section_5_4_realistic_dialogue_outline.md ← 真实对话版 5.4 新提纲与术语表
└── results/
    └── (运行后收集的产物放这里)
```

---

## 1. 环境搭建

### 1.1 前置要求

- Windows 10/11
- PowerShell 5.1+
- conda (Miniconda/Anaconda)
- QGIS 3.40.11 (`C:\Program Files\QGIS 3.40.11`)
- Kimi Code API key（或你 agent 自己配好的其他 LLM provider）
- Git

### 1.2 克隆与安装

```powershell
# 1. 克隆仓库
git clone https://github.com/xuanniao57/UrbanAgents.git D:/UrbanAgents_Case2
cd D:/UrbanAgents_Case2

# 2. 切换到 Urban-Hermes 分支
git checkout feature/hermes-urban-research-memory-qgis

# 3. 确保分支包含 delegation 和 memory reflection 修复
#    如果 git log -1 --oneline 显示的不是 d0f684b 或更新，联系上游

# 4. 创建 conda 环境
conda create -n urban-hermes-case2 python=3.11 -y
conda activate urban-hermes-case2

# 5. 安装 Urban-Hermes（editable 模式）
#    注意：Urban-Hermes 入口在 paper4_urban_svgagent/hermes_urban_agent/
cd paper4_urban_svgagent
pip install -e .

# 6. 验证安装
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
python -m urban_hermes.launcher --list-tools --plain
# 应输出 21 个工具，包含 delegate_task 和 urban_memory_reflect
```

### 1.3 配置 Kimi Code API Key

> **安全说明：** 这个共享包不包含真实 API key。请协作者把自己的 key 写入本地 `env/kimi_code.env`。不要把真实 `.env`、`kimi_code.env`、截图或终端输出打包回传。

```powershell
# 进入 Case2 测试包根目录。
# 如果你按本文档安装，建议把本包放到：
# D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run

# 复制 env 模板并填入你自己的 Kimi Code API key
Copy-Item .\env\kimi_code.env.example .\env\kimi_code.env -Force
notepad .\env\kimi_code.env

# 在当前 PowerShell 进程中加载 API key 和兼容别名
. .\scripts\load_kimi_code_env.ps1 -EnvFile .\env\kimi_code.env

# 创建干净的 Hermes 配置目录（避免旧 auth 缓存干扰）
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/hermes_home"
mkdir -Force $env:HERMES_HOME

# 写入 Hermes 配置。Kimi Code provider 不需要把 base_url 指到 Moonshot CN chat-completions。
@"
model:
  default: kimi-for-coding
  provider: kimi-coding
toolsets:
- hermes-cli
agent:
  max_turns: 90
terminal:
  backend: local
"@ | Out-File -FilePath "$env:HERMES_HOME\config.yaml" -Encoding utf8
```

### 1.4 运行前环境变量

每次启动 Urban-Hermes 前在 PowerShell 中执行：

```powershell
conda activate urban-hermes-case2
Set-Location D:/UrbanAgents_Case2/paper4_urban_svgagent
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "$PWD\hermes_urban_agent;$PWD"
$env:HERMES_HOME = "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/hermes_home"
$env:URBAN_AGENT_HOME = "$PWD\.urban-agent"
. D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/scripts/load_kimi_code_env.ps1 -EnvFile D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/env/kimi_code.env

# 冒烟测试
python -m urban_hermes.launcher "say hello in one word" --provider kimi-coding --model kimi-for-coding --max-turns 1 --yolo
# 应输出正常回复，不报 401 或 Context length exceeded
```

---

## 2. 数据画布

### 2.1 你需要在运行前准备什么

在你的本地创建 `D:/UrbanAgents_Case2_Data` 目录，放入以下文件：

| 文件 | 必需？ | 作用 | 要求 |
|---|---|---|---|
| `aoi.geojson` | **必需** | 研究区边界 | 权威来源，含 CRS 信息 |
| `spatial_units.geojson` | **必需** | 空间分析单元 | 街段/网格/街区 polygon |
| `streetview_perception.csv` | **必需** | 街景感知分数 | 至少含 `beautiful`, `lively`, `safe`, `green` 字段 + 坐标 |
| `osm_roads.geojson` | 推荐 | 路网 | OSM 或本地缓存 |
| `buildings.geojson` | 推荐 | 建筑轮廓 | OSM 或本地缓存 |
| `observed_outcome.csv` | 可选 | 真实 Y 变量 | 人流/签到/问卷/评分 |
| `poi.geojson` | 可选 | POI | 功能供给 proxy |
| `metadata.json` | 推荐 | 数据说明 | 来源、日期、字段、CRS、时间窗口 |

### 2.2 最小可用数据画布（如果你没有真实数据）

如果你没有任何现成数据，用以下方法构造最小画布（仅用于流程验证，不是真实分析）：

```
# 用南京路或外滩区域构造
# AOI: 从 paper9 数据中复制一个 district boundary
# spatial_units: 用 200m 网格生成
# streetview_perception: 从本地街景批次中抽取点 + 随机生成模拟的 beautiful/lively/safe/green 分数（明确标注 SIMULATED）
# osm_roads / buildings: 从 OSM 缓存复制
# observed_outcome: 不存在 → 诚实标注为 missing
```

**重要：** 如果 `observed_outcome.csv` 不存在，Urban-Hermes 必须把原始问题中的"城市活力/步行体验/公共空间质量"改为 proxy/missing，不能假装有 Y 变量。这正是 Case 2 要测试的 Gap 1 行为。

---

## 3. 运行流程

Case 2 正式推荐使用 **真实对话版 4 阶段流程**。每轮之间你（测试者）检查产物，决定是否自然纠正。旧的 5 轮 full-prompt 流程保留在后文作为 smoke test 或对照。

### 3.0 正式推荐：真实对话版流程

外部 agent 操作规约：`AGENT_TESTER_OPERATOR_GUIDE.md`

安装验收清单：`INSTALL_LATEST_URBAN_HERMES.md`

入口文档：`COLLABORATOR_REALISTIC_TEST_README.md`

脚本文档：`prompts/case2_realistic_research_dialogue_script.md`

逐轮 prompt：`prompts/realistic_dialogue/`

```
阶段         | 会话动作              | 目的
-------------|----------------------|------
Turn 1       | 模糊研究想法          | 让 Urban-Hermes 自主盘点数据、方法需求、运行环境与算力
Turn 2A      | 3D/5D 建成环境设计    | 先不加入街景感知，只设计经典建成环境实验流程
Turn 2B      | 人确认后执行          | 执行第一版，不能做的模型必须停止或降级
Turn 3       | GWR/GWRF + reviewer  | 以空间非平稳性、非线性、PDP/SHAP 为诱导，观察审查门控与自我纠正
Turn 4       | 加入主观街景感知      | 做第二版，并与只用建成环境 3D/5D 的版本比较
```

**关键操作原则：** 不要把 expected behavior 粘给 Urban-Hermes。合作者只复制每个 prompt 文件里的短句。测试目标是观察 Urban-Hermes 是否自己补齐城市科学研究流程，而不是测试它能否复述一段完整 protocol。

如果由 OpenClaw、Claude Code 或其他本地 agent 代跑，必须先读 `AGENT_TESTER_OPERATOR_GUIDE.md`。该 agent 的职责是安装、运行、记录、验收和打包回传，不得替 Urban-Hermes 手工完成城市分析。

Turn 1 示例命令：

```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/realistic_dialogue/turn1_scoping.md" -Raw
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 12 --yolo --toolsets urban,todo,memory `
  2>&1 | Out-File -FilePath "D:/UrbanAgents_Case2_Output/realistic_dialogue/turn1_scoping/cli_transcript_turn1_utf8.txt" -Encoding utf8
```

后续轮次建议使用同一 session 的 `--resume SESSION_ID`，并分别保存到 `D:/UrbanAgents_Case2_Output/realistic_dialogue/turn2a_design/`、`turn2b_execute/`、`turn3_gwr_gwrf_review/` 和 `turn4_perception_extension/`。

### 3.1 旧流程：完整 prompt smoke test 或对照

以下流程仍可用于 smoke test、对照或消融，但不再作为合作者正式 5.4 主流程。

```
轮次         | 会话类型        | 目的
------------|----------------|------
Round 1     | 新会话          | 完整 Case 2 执行（Gap 1 + Gap 2 一次性触发）
Tester Check| 测试者检查       | 检查产物，找出需要纠正的问题
Correction  | 纠正会话         | 窄范围纠正 + 写入 feedback memory
Round 2     | 新会话（memory on）| 同一任务重跑，检验纠正是否被复用
Control     | 新会话（memory off）| 消融：拿掉 memory，观察退化
```

### 3.1.1 旧 Round 1：完整执行

**输入 prompt**（`prompts/case2_full_prompt.md`）：

```text
我想做一个街景感知相关的城市分析：判断街景感知指标是否可以和某类城市活力、
步行体验或公共空间质量指标放在同一空间单元上分析，并探索它们之间是否存在
非线性关系或空间异质性。

请把 D:/UrbanAgents_Case2_Data 当作本次研究的数据画布，
把结果保存到 D:/UrbanAgents_Case2_Output/full_run。

请你自己先判断这个研究问题是否可做：需要哪些 Y、哪些街景感知 X、
哪些客观建成环境控制变量、什么空间单元、什么时间窗口，
以及当前数据能支持到什么程度。

请像一个 Urban Agents 工作流一样自主完成：
- 先厘清研究问题、变量、空间单元和证据缺口
- 再选择合适的数据处理、GIS、统计或机器学习方法
- 方法可以包括数据盘点、字段/CRS/范围检查、空间连接、相关性、
  非线性诊断、随机森林/解释性分析、空间分组、热点或局部异质性诊断
- 只有在数据和工具都足够时才尝试更复杂的空间加权模型

过程中请特别注意：
- 街景感知不是人流或活力观测
- POI、设施数量、商业供给只能作为功能供给或活动机会的 proxy
- 缺少明确时间窗口时不能声称昼夜、工作日或时段差异
- 相关性和机器学习解释不能写成因果影响
- 不要在 CRS、范围、字段或空间单元对齐没有检查前开始建模

如果关键 Y、街景感知字段、空间单元或时间窗口缺失，
请诚实终止或降级研究问题，而不是硬做模型。

请生成可检查的中间产物和一份中文报告。
报告里说明你读取了什么数据、生成了什么文件、
哪些指标是 direct/proxy/missing、采用了什么方法、
方法操作中有什么风险、结论能支持到什么程度，
以及你从本次任务中记录了什么可复用经验。
```

**启动命令：**

```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/case2_full_prompt.md" -Raw
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 25 --yolo --toolsets urban,todo,memory `
  2>&1 | Tee-Object -FilePath "D:/UrbanAgents_Case2_Output/full_run/cli_transcript_round1.txt"
```

**预期发生什么（Gap 1 的证据）：**

1. Urban-Hermes 调用 `urban_host_fs` 读取 `D:/UrbanAgents_Case2_Data` 下的文件
2. 它调用 `urban_ground_task` 或自行判断：是否有真实 Y？街景感知是什么角色？空间单元是否可用？
3. 它产出一张 direct/proxy/missing 表——如果 `observed_outcome.csv` 不存在，Y 应该标记为 missing，街景感知标记为 perceptual X（不是 observed Y）
4. 它生成一个 `spatial_reasoning_manifest.json` 或等价的证据清单
5. **问题 1：** 它可能仍然把街景感知当作 Y 变量或把相关分析写成因果——这就是你要在 Tester Check 里抓的问题

**预期发生什么（Gap 2 的证据）：**

6. 它生成中间空间产物：clipped GeoJSON、grid CSV、路网节点/边等
7. 如果有 QGIS，它生成 `.qgs/.qgz` 工程
8. 它输出一份中文报告 `final_report.md`
9. **问题 2：** QGIS 工程可能有 invalid layers、renderer 字段不对、manifest schema 不合规——这就是独立 validator 要抓的问题

**Tester Check 检查清单：**

- [ ] 打开 `D:/UrbanAgents_Case2_Output/full_run/`，列出所有生成文件
- [ ] 通读 `final_report.md`：是否区分了街景感知（X）和城市 outcome（Y）？
- [ ] 检查 direct/proxy/missing 表：POI 是否标为 proxy？缺少 Y 时是否诚实？
- [ ] 检查是否有 unsupported claim（如"活力显著提升"、"因果关系"、"昼夜差异"）
- [ ] 如果有 `.qgs/.qgz`，用 QGIS 打开看是否能正常加载
- [ ] 跑独立 QGIS 验证脚本
- [ ] 记录所有发现到 `tester_evaluation_round1.md`

---

### 3.1.2 旧 Tester Check + 纠正

**纠正 prompt**（`prompts/case2_correction_feedback.md`）：

```text
这是对刚才 Case2 街景感知分析运行结果的测试者纠错反馈。

上一次输出目录：D:/UrbanAgents_Case2_Output/full_run
请把修订结果保存到：D:/UrbanAgents_Case2_Output/correction

我发现一组需要你以后复用的规则：
1. 街景感知分数描述的是视觉环境或主观感知代理变量，
   不是人流、活力、步行体验或公共空间质量的直接观测。
2. POI、设施数量、商业供给或兴趣点热度只能作为功能供给或
   活动机会的 proxy，也不能直接替代手机信令、客流计数、签到、
   问卷评分、行为观察或其他真实 Y 变量。
3. 如果缺少明确时间窗口，不能声称昼夜差异、工作日差异或时段异质性。
4. 如果只做相关性或机器学习解释，也不能写成因果影响。
5. 如果关键 Y、街景感知字段、空间单元或时间戳缺失，
   应该终止、降级研究问题，或只输出数据可计算性审计。

请你做三件事：
1. 修订刚才的 direct/proxy/missing 指标表和中文报告，
   明确哪些结论被降级、删除或改写为 proxy。
2. 把这条纠正写入可复用的 feedback/research memory
   （使用 urban_record_feedback 或 urban_memory_record），
   便于下一次相同或相近任务自动召回。
3. 明确说明下一次面对同样输入时，
   你会如何在建模前更早地使用这条经验。
```

**启动命令：**

```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/case2_correction_feedback.md" -Raw
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 10 --yolo --toolsets urban,todo,memory `
  2>&1 | Tee-Object -FilePath "D:/UrbanAgents_Case2_Output/correction/cli_transcript_correction.txt"
```

**预期信号（成功纠正的标志）：**

- 修订报告中街景感知从 Y 被重新分类为 X 或 proxy
- POI 被标注为 proxy，不再以"活力"描述
- 缺少时间窗口时不再出现 temporal 声称
- `urban_record_feedback` 或 `urban_memory_record` 被调用
- 回复中包含"下一次遇到同样输入时会先检查..."的声明

---

### 3.1.3 旧 Round 2：纠正后重跑（memory on）

用**同一个** prompt 文本，但存到新输出目录。

**启动命令：**

```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/case2_full_prompt.md" -Raw
# 手动把 prompt 中的 D:/UrbanAgents_Case2_Output/full_run 替换为 D:/UrbanAgents_Case2_Output/round2_after_feedback
$query = $query.Replace("full_run", "round2_after_feedback")
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 20 --yolo --toolsets urban,todo,memory `
  2>&1 | Tee-Object -FilePath "D:/UrbanAgents_Case2_Output/round2_after_feedback/cli_transcript_round2.txt"
```

**预期信号（Gap 2 + memory 的证据）：**

- 这次执行中，Urban-Hermes 在分析初期就更早标注了 proxy/missing
- 街景感知不再被当作 Y 使用
- 如果没有真实 Y，它应该诚实说"本次只能做 X 侧审计，不能做 Y-X 建模"
- 报告中引用或体现上一次 feedback memory 的内容
- 与 Round 1 相比，unsupported claims 减少

---

### 3.1.4 旧 Control：无记忆对照（memory off）

**启动命令：**

```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/case2_full_prompt.md" -Raw
$query = $query.Replace("full_run", "no_memory_control")
python -m urban_hermes.launcher $query `
  --provider kimi-coding --model kimi-for-coding `
  --max-turns 20 --yolo --toolsets urban,todo `
  2>&1 | Tee-Object -FilePath "D:/UrbanAgents_Case2_Output/no_memory_control/cli_transcript_control.txt"
```

注意：`--toolsets urban,todo` **不包含 `memory`**。

**预期信号（Gap 3 的反面证据）：**

- 与 Round 2 相比，这次更可能再次把街景感知当 Y 用、POI 当活力写、出现因果表述
- 没有从 feedback memory 中检索到上次的纠正规则
- 这在 5.5 节中作为"无记忆时经验无法跨任务复用"的对照证据使用

---

### 3.1.5 旧消融实验（可选，为 5.5 提供补充证据）

如果你需要更丰富的 Gap 1/2 消融证据，可以额外跑以下三轮。

**A1: w/o Urban Toolset**（`prompts/ablation/a1_no_urban_toolset.md`）
```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/ablation/a1_no_urban_toolset.md" -Raw
$query = $query.Replace("{{CASE2_DATA_ROOT}}", "D:/UrbanAgents_Case2_Data")
$query = $query.Replace("{{CASE2_OUTPUT_ROOT}}", "D:/UrbanAgents_Case2_Output")
python -m urban_hermes.launcher $query --provider kimi-coding --model kimi-for-coding --max-turns 15 --yolo --toolsets todo 2>&1 | Tee-Object "D:/UrbanAgents_Case2_Output/ablation_a1_transcript.txt"
```

**A2: w/o Grounding and Review**（`prompts/ablation/a2_no_ground_review.md`）
```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/ablation/a2_no_ground_review.md" -Raw
$query = $query.Replace("{{CASE2_DATA_ROOT}}", "D:/UrbanAgents_Case2_Data")
$query = $query.Replace("{{CASE2_OUTPUT_ROOT}}", "D:/UrbanAgents_Case2_Output")
python -m urban_hermes.launcher $query --provider kimi-coding --model kimi-for-coding --max-turns 15 --yolo --toolsets urban,todo 2>&1 | Tee-Object "D:/UrbanAgents_Case2_Output/ablation_a2_transcript.txt"
```

**A3: w/o Memory**（`prompts/ablation/a3_no_memory.md`）
```powershell
$query = Get-Content "D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/prompts/ablation/a3_no_memory.md" -Raw
$query = $query.Replace("{{CASE2_DATA_ROOT}}", "D:/UrbanAgents_Case2_Data")
$query = $query.Replace("{{CASE2_OUTPUT_ROOT}}", "D:/UrbanAgents_Case2_Output")
python -m urban_hermes.launcher $query --provider kimi-coding --model kimi-for-coding --max-turns 15 --yolo --toolsets urban,todo 2>&1 | Tee-Object "D:/UrbanAgents_Case2_Output/ablation_a3_transcript.txt"
```

---

## 4. QGIS 独立验收

**验收脚本**已在 `qgis_validation/validate_case_qgis.py`。

每次 Urban-Hermes 声称生成了 QGIS 工程后，用 QGIS 自带的 Python 运行：

```powershell
& 'C:\Program Files\QGIS 3.40.11\bin\python-qgis-ltr.bat' `
  'D:/UrbanAgents_Case2/paper4_urban_svgagent/experiments/case2_run/qgis_validation/validate_case_qgis.py' `
  'D:/UrbanAgents_Case2_Output/full_run/qgis_workspace' `
  --output 'D:/UrbanAgents_Case2_Output/full_run/artifact_validation_independent.json'
```

**通过标准：**

```json
{
  "qgis_read_ok": true,
  "invalid_layers": [],
  "missing_datasources": [],
  "missing_core_renderer_fields": [],
  "basemap_last": true,
  "valid_layers_count": ">= 4"
}
```

如果任何一个条件不满足 → 不接受产物，写入纠正 prompt 要求修复。

---

## 5. 撰写 5.4 节

### 5.1 5.4 在论文中的位置

按一份 CEUS 风格论文第五章的典型结构：

```
5.1  实验目标：从回答正确到产物可验证
5.2  实验设置（十任务 + 两组互补实验）
5.3  过程证据：Grounding quiz 与空间推理验证闭环
5.4  Case 2：街景感知分析的输入锚定与推理可验证性   ← 你写这个
5.5  两层记忆：从单案纠错到跨任务累积
5.6  十任务结果与诊断性消融
5.7  讨论与限制
```

### 5.2 5.4 的论证结构

5.4 主要展示 **Gap 1 和 Gap 2**，不要跨到 Gap 3。论证分为三段：

**第一段：Case 2 的任务设定**
- 一个更短、更自然的街景感知任务
- 数据画布中有/没有真实 Y 变量是实验的关键控制点
- Round 1：让 Urban-Hermes 在自然条件下运行，观察它是否自发做 grounding

**第二段：Gap 1 —— 输入锚定的证据**
- 引用 Round 1 的 transcript 和产物
- 展示 Urban-Hermes 如何判断数据画布中有没有 Y、街景感知是什么角色
- 如果它犯错（把街景感知当 Y、POI 当活力），也要写——这是 grounding 失败的证据
- 纠正后（Round 2）的对比：同任务下更早的 proxy 标注、更诚实的研究问题降级
- **可用的图/表：** direct/proxy/missing 指标分类表、Round 1 vs Round 2 的 evidence manifest 对比

**第三段：Gap 2 —— 推理可验证性的证据**
- 引用中间空间产物：clipped GeoJSON、200m 网格 CSV、QGIS 工程
- 引用独立 QGIS validator 的验收 JSON
- 如果有 validator 发现的问题（invalid layer、renderer 字段不对）→ 展示纠正前后
- 如果模型没有生成 QGIS → 诚实写"本 case 未完成 QGIS 工程，空间推理仅通过中间 GeoJSON 检查"
- **可用的图：** QGIS workspace overlay 截图、validator JSON 的 before/after 对比、grounding quiz to artifact validation 流程图

### 5.3 行文语气要求

- 不要写"模型很强"或"模型很弱"
- 写"Urban-Hermes 在 Round 1 中做了 X，这在 Y 条件下导致了 Z"
- 失败也是证据——展示系统在什么条件下暴露了什么问题
- 所有结论都要能追溯到 transcript 行号或产物文件路径

### 5.4 引用你在本实验中产生的文件

在 5.4 中引用时，使用论文友好路径：

| 实际路径 | 论文引用方式 |
|---|---|
| `D:/UrbanAgents_Case2_Output/full_run/cli_transcript_round1.txt` | "Round 1 CLI transcript" |
| `D:/UrbanAgents_Case2_Output/full_run/final_report.md` | "Round 1 final report" |
| `D:/UrbanAgents_Case2_Output/correction/cli_transcript_correction.txt` | "Tester correction transcript" |
| `D:/UrbanAgents_Case2_Output/round2_after_feedback/cli_transcript_round2.txt` | "Round 2 CLI transcript" |
| `D:/UrbanAgents_Case2_Output/full_run/artifact_validation_independent.json` | "QGIS independent validation" |

---

## 6. 每轮测试员评估记录模板

每轮结束后填写，保存在 `results/` 下。

```markdown
# Case 2 Round <N> 测试员评估记录

## 运行信息
- 时间：
- 模型：kimi-for-coding（provider: kimi-coding）
- 会话 ID：<从 CLI 输出中提取>
- Max turns：
- Transcript 文件：

## 产物清单
- [ ] final_report.md 存在？内容是否可读？
- [ ] direct/proxy/missing 表 存在？
- [ ] .qgs/.qgz 存在？
- [ ] grid CSV/GeoJSON 存在？
- [ ] spatial_reasoning_manifest.json 存在？

## 关键问题检查
- [ ] 街景感知是否被误当作 Y 变量？
- [ ] POI 是否被标为 proxy 而非直接观测？
- [ ] 缺少时间窗口时是否仍有 temporal 声称？
- [ ] 相关/ML 解释是否写成了因果？
- [ ] CRS/字段/空间单元是否在建模前被检查？

## QGIS 验收
- qgis_read_ok:
- invalid_layers:
- missing_datasources:
- renderer_bound_fields:

## 测试员判断
[Accepted / Needs correction / Failed]

## 下一轮行动
- 如果 Accepted → 进入 Round 2 或写 5.4
- 如果 Needs correction → 发纠正 prompt，具体问题：...
- 如果 Failed → 记录失败原因，判断是否需要重跑
```

---

## 7. 常见问题与对策

### Q1: Urban-Hermes 报告中文乱码
→ 检查 `$env:PYTHONUTF8 = "1"` 和 `$env:PYTHONIOENCODING = "utf-8"` 是否设置。
→ 如果产物文件乱码，让 Urban-Hermes 用 `urban_host_python` 重新以 UTF-8 写入。

### Q2: Kimi API 返回 401
→ 检查 `env/kimi_code.env` 中的 `KIMI_CODE_API_KEY` 是否正确，并确认已执行 `scripts/load_kimi_code_env.ps1`。
→ 删除 `$env:HERMES_HOME\auth.json`（如果有旧缓存）。
→ 用第 1.4 节的 Urban-Hermes 冒烟测试验证；不要用 Moonshot CN `/v1/models` 来验证 Kimi Code key。

### Q3: Context length exceeded (8k tokens)
→ 确认命令使用 `--provider kimi-coding --model kimi-for-coding`。
→ 如果仍然超限，缩短 prompt 或减少 `--max-turns`。
→ 不要把 Case 2 切回 8k chat-completions 模型。

### Q4: Urban-Hermes 生成了 QGIS 但 validator 报 missing datasource
→ 这是常见问题。纠正 prompt 应该窄：只要求修复具体的数据源路径，不要重算指标。

### Q5: 我没有真实街景数据
→ 用模拟数据是可以的，但必须在论文中标注"simulated data for workflow demonstration"。
→ 关键是 Urban-Hermes 的行为是否正确（它是否诚实标注了数据限制），而不是数据本身是否权威。

---

## 8. 交付物清单

跑完所有轮次后，你需要交付给论文撰写者：

| 交付物 | 格式 | 用途 |
|---|---|---|
| 所有轮次的 CLI transcript | `.txt` | 5.4 中的流程证据和引用 |
| Round 1 的 final_report.md | `.md` | 展示 Gap 1 的自然行为 |
| 纠正后的 final_report.md | `.md` | 展示 Gap 1 纠正效果 |
| direct/proxy/missing 表（Round 1 + Round 2） | `.csv` 或 `.md` | 5.4 中的核心证据表 |
| QGIS 独立验证 JSON（before + after） | `.json` | 展示 Gap 2 的验证闭环 |
| QGIS workspace overlay 截图 | `.png` | 5.4 的配套图 |
| 每轮测试员评估记录 | `.md` | 撰写参考 |
| 5.4 节草稿 | `.md` | 论文成品 |

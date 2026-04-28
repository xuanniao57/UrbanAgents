# UrbanAgent Web Interface

轻量化的城市空间分析交互式前端，配合 UrbanAgent 后端实现 Human-AI 协作分析。

## 快速启动

```bash
cd web
pip install -r requirements.txt
python app.py
```

浏览器访问 `http://127.0.0.1:8765`

## 架构

```
web/
├── app.py                  # FastAPI 后端 + WebSocket
├── requirements.txt
├── README.md
└── static/
    ├── index.html          # 主页面
    ├── css/style.css       # 样式
    └── js/app.js           # 前端逻辑
```

## 交互模式

| 模式 | 说明 |
|------|------|
| 🔍 引导模式 (Guided) | 每个决策点暂停等待用户确认，适合探索性分析 |
| 📋 监督模式 (Supervisory) | 自动执行但生成检查点报告，适合批量任务 |
| ⚡ 自主模式 (Autonomous) | 全自动运行，适合已验证的分析流程 |

## 六个决策检查点 (DP-1 ~ DP-6)

1. **DP-1 任务理解** — 确认分析意图、范围和目标
2. **DP-2 数据源确认** — 验证数据获取计划
3. **DP-3 空间结构审查** — 审查拓扑图和向量表示
4. **DP-4 干预方案选择** — 评估和筛选空间干预建议
5. **DP-5 参数调优** — 调整分析参数阈值
6. **DP-6 结果解读** — 审阅结论摘要，补充领域知识

## 技术栈

- **后端**: FastAPI + WebSocket
- **前端**: 原生 HTML/CSS/JS（零构建依赖）
- **地图**: Leaflet.js + CARTO 暗色底图
- **通信**: WebSocket 实时双向通信

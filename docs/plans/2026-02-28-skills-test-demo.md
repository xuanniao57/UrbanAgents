# AcademicForge Skills 功能测试演示

> 本文档用于验证已安装的 AcademicForge skills 是否可以正常工作

## 已安装的 Skills

### 1. superpowers 系列 (14个)
- `brainstorming` - 需求收敛与设计探索
- `writing-plans` - 编写详细实施计划
- `executing-plans` - 执行计划任务
- `systematic-debugging` - 系统化调试
- `test-driven-development` - 测试驱动开发
- `verification-before-completion` - 完成前验证
- `writing-skills` - 编写 skills
- 以及 7 个其他工程管理技能

### 2. humanizer
- 去除AI写作痕迹，使文本更像人类写作

---

## 测试用例设计

### 测试 1: Brainstorming Skill 测试
**场景**: 用户想要添加一个新功能，但需求不明确
**预期**: Skill 应该引导用户澄清需求，提出2-3个方案，并在用户确认后才进入实施

### 测试 2: Writing-Plans Skill 测试
**场景**: 已有一个明确的设计，需要转化为可执行的计划
**预期**: Skill 应该生成详细的任务列表，包含具体文件路径、代码、测试命令

### 测试 3: Humanizer Skill 测试
**场景**: 有一段典型的AI生成的学术文本需要润色
**预期**: Skill 应该识别并修复AI写作模式，使文本更自然

---

## 如何触发测试

你可以通过以下方式测试这些 skills：

1. **测试 Brainstorming**: 
   - 说："我想给项目添加一个新功能"
   - 观察我是否先询问需求，而不是直接写代码

2. **测试 Writing-Plans**:
   - 说："帮我制定一个实施计划"
   - 观察我是否生成结构化的计划文档

3. **测试 Humanizer**:
   - 提供一段AI风格的文本，说："请润色这段文字"
   - 观察我是否使用 humanizer skill 改进文本

---

*测试文档生成时间: 2026-02-28*

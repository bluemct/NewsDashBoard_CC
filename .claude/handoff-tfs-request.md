# TFS Request 智能管理 — Handoff 文档

**最后更新**: 2026-07-31 17:00
**状态**: ✅ 核心功能完成 — TSGLog 字段修复、批量 AI 分析（仅 Assigned To Implementer）、页面响应式布局

---

## 1. 项目目标

在 PS Workspace 中实现 TFS Request 2010 工单的三步走智能管理流程：

1. **获取 Open 工单** → 显示工单列表（ID, 标题, 状态, 指派人, Property, 更新时间）
2. **AI 智能分析** → 只对 "Assigned To Implementer" 工单批量调用 AI，返回 Property/Solution(英文)/工时/AssignTo
3. **人工确认后更新** → 可编辑表格（黄色高亮 AI 建议），灰色显示已跳过工单，逐工单写入 TFS

---

## 2. 核心设计决策

### 数据源
- TFS `System.Description` 字段全部为空
- **实际数据来自 `Hisoft.21ViaNet.Description`**（邮件往来 HTML），**不是** `Hisoft.21ViaNet.TSGLog`
- Python 后端 `_strip_html()` 剥离 HTML 标签后送入 AI

### 分类（AI + 关键词回退）
- **17 个 Property 类别**（18 含 PS-Other）
- AI prompt 全英文，solution 返回英文
- AI 失败时关键词匹配回退

### AssignTo 提取
- AI 批量 prompt 内置 assignee 映射，直接返回 `assigned_to`
- 代码 `_extract_assigned_to()` 作为回退（正则提取 From 行邮箱）
- 6 人邮箱→姓名映射表

### AI 批量调用策略
- `_classify_batch_ai()` 默认一次性发送所有工单
- prompt 超 8000 字符自动拆分批次
- `max_tokens=8000`（Qwen reasoning model）
- **只分析 "Assigned To Implementer" 工单**，"In Process Implementer" 等状态跳过

### 前端布局
- 所有页面 `width:100%; max-width:1500px`，响应式填充大屏空间
- 分析结果表格：🟡 黄色 = AI 分析（可编辑），⚪ 灰色 = 已跳过（只读）

---

## 3. 已完成的工作

### 3.1 数据链路修复
- PowerShell WITQL 查询字段名从 `Hisoft.21ViaNet.TSGLog` 改为 `Hisoft.21ViaNet.Description`
- query 返回增加 `property` 字段
- TSGLog 强制 `[string]` 转换 + 截断 5000 字符

### 3.2 后端 AI 分类（`PSWorkspace/routes/tfs.py`）
- `_classify_batch_ai()` — 批量 AI，动态分批，返回 4-tuple (prop, sol, wh, assigned_to)
- `_classify_ticket_ai()` — 单条 AI 分类
- `_classify_by_keywords()` — 17 类别关键词回退，返回 4-tuple
- `_extract_assigned_to()` — 代码回退提取邮箱
- `_strip_html()` — HTML 转纯文本
- AI prompt 全英文（`_AI_SYSTEM_PROMPT`, `_AI_CATEGORY_DESC` 等）

### 3.3 后端 API 端点
- `batch-classify` — 只分析 Assigned To Implementer，返回 `skipped` 标记
- `batch-apply` — 只更新非 skipped 工单

### 3.4 前端（`PSWorkspace/templates/index.html`）
- 原始表格显示 Property 列
- 分析结果表格：双色行（黄色可编辑 / 灰色只读）
- 不自动获取工单，仅手动点击按钮触发

---

## 4. 修改文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `PSWorkspace/routes/tfs.py` | ✅ 已改 | 批量 AI、全英文 prompt、状态过滤、4-tuple 返回 |
| `PSWorkspace/templates/index.html` | ✅ 已改 | 双色表格、响应式布局、手动触发获取 |
| `TfsRequestPS/TfsRequest.ps1` | ✅ 已改 | 字段名修复、Property 字段、TSGLog 修正 |
| `.claude/skills/tfs-request/SKILL.md` | ✅ 已改 | 更新为 v3 文档 |

---

## 5. 关键代码位置

### PSWorkspace/routes/tfs.py

| 函数/端点 | 行号 |
|---|---|
| `_run_tfs_ps()` | 237 |
| `_strip_html()` | 337 |
| `_ASSIGNEE_MAP` | 352 |
| `_extract_assigned_to()` | 362 |
| `_classify_ticket()` | 412 |
| `_AI_SYSTEM_PROMPT` (英文) | 450 |
| `_AI_CATEGORY_DESC` (英文) | 457 |
| `_build_batch_user_content()` | 509 |
| `_classify_batch_ai()` | 550 |
| `_classify_ticket_ai()` | 676 |
| `_classify_by_keywords()` | 870 |
| `request_batch_classify()` | 955 |
| `request_batch_apply()` | 1050 |

### TfsRequestPS/TfsRequest.ps1

| 代码段 | 行号 |
|---|---|
| WITQL 查询（含 Property、Hisoft.21ViaNet.Description） | 155 |
| query 返回（含 property） | 185 |

---

## 6. 已知问题

- **重复 except 块**：`_classify_batch_ai()` 第 667-673 行有重复的 `except ImportError/Exception`（复制粘贴残留），不影响功能

---

## 7. 下一步

1. 端到端测试：获取工单 → AI 分析 → 确认更新 → 验证 TFS 写入正确
2. 观察 AI 批量响应质量（英文 solution 是否准确）
3. 用户反馈收集后调整 prompt 或分类规则

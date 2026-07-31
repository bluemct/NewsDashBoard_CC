# TFS Request 智能管理 — Handoff 文档

**最后更新**: 2026-07-31 18:30
**版本代号**: Friday
**状态**: ✅ 功能完成 — 等待用户端到端验证

---

## 1. 项目目标

在 PS Workspace 中实现 TFS Request 2010 工单的三步走智能管理流程：
1. **获取 Open 工单** → 显示工单列表（筛选、排序、ID 点击跳转编辑）
2. **AI 智能分析** → 只对 "Assigned To Implementer" 批量 AI 分析，返回 Property/Solution(英文)/工时/AssignTo
3. **人工确认后更新** → 黄色可编辑 + 灰色跳过，逐工单写入 TFS

---

## 2. 修改文件清单

| 文件 | 说明 |
|------|------|
| `PSWorkspace/routes/tfs.py` | 全英文 AI prompt、状态过滤、4-tuple 返回、PowerShell 传参修复 |
| `PSWorkspace/templates/index.html` | 双色表格、响应式布局 (1500px)、筛选、排序、跳转编辑、placeholder onfocus |
| `TfsRequestPS/TfsRequest.ps1` | 字段名修复、Property/Solution/WorkingHour 字段、WorkItemIds 字符串解析 |
| `.claude/skills/tfs-request/SKILL.md` | v4 文档 |

---

## 3. 前端功能

| 功能 | 说明 |
|------|------|
| 筛选框 | 搜索 ID/指派人/Property + 状态下拉筛选，实时过滤 |
| 排序 | 点击 ID/状态/指派人/Property 列头，正反序切换 |
| 点击 ID 跳转 | 蓝色可点击 ID → 自动切到"单个工单编辑"，回填所有字段 |
| 批量 Resolve | 自动带入已获取工单 ID |
| placeholder onfocus | 点击空白输入框自动填入 placeholder 文字 |
| 响应式布局 | max-width: 1500px，大屏填充 |

---

## 4. 关键代码位置

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
| `Convert-WorkItemIds` | 65 |
| WITQL 查询 | 155 |
| query 返回（含 property/solution/workingHour） | 196 |

---

## 5. 已知问题

- **重复 except 块**：`_classify_batch_ai()` 有重复 `except ImportError/Exception`（残留代码），不影响功能
- **PowerShell 5.1 函数返回值展开** — 已修复：所有返回值用 `@()` 包裹

---

## 6. 下一步

1. 用户端到端测试：获取 → AI 分析 → 确认更新 → 验证 TFS 写入
2. 观察 AI 响应质量（英文 solution 是否准确）
3. 收集反馈后调整 prompt 或分类规则

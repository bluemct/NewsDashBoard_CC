# sync

同步更新所有 skill SKILL.md 和 memory 文件，使其反映代码库当前状态。

## When to use

用户输入「更新skill & memory」、「更新skill和memory」、「sync skill memory」或类似指令。

## What to do

### 1. 读取当前代码

读取以下核心文件，了解最新实现：
- `verify_list_contacts.py` — 验证模块（project root）
- `deep_verify_list.py` — 深验证模块（project root）
- `edm_gui.py` — GUI 主程序（project root）
- `.claude/skills/edm-process/edm_process.py` — EDM 处理核心

### 2. 更新 Skill 文件

逐个检查 `.claude/skills/*/SKILL.md`，对比代码实际实现：
- `edm-deep-verify/SKILL.md` — 深验证 skill
- `edm-process/SKILL.md` — EDM 处理 skill

确保每个 SKILL.md 准确描述：
- 当前实现方式（API 调用方式、分页策略、并行/串行）
- 公共函数列表和参数
- CLI 用法
- 关键发现（API 限制、参数格式等）
- 文件路径

### 3. 更新 Memory 文件

读取 `.claude/projects/*/memory/MEMORY.md` 定位相关文件，然后更新：

| Memory 文件 | 更新内容 |
|-------------|---------|
| `edm-gui-tool.md` | GUI 功能、按钮行为、验证方式、Import 自动验证逻辑 |
| `list-verify-feature.md` | 验证方式、公共函数、API 发现、变更说明 |
| `deep-verify-feature.md` | 深验证方式、公共函数、与 email-only 区别 |
| `MEMORY.md` | 确保每个条目描述准确反映当前状态 |

更新原则：
- 描述必须与代码一致，不要保留过时的信息
- 记录重要的 API 发现（分页限制、参数格式等）
- 保留关联记忆链接 `[[name]]`
- 更新 `originSessionId` 为 current 或保留原始值

### 4. 验证

最后检查：
- `python edm_gui.py` 能正常 import（不启动 GUI，只验证导入）
- 所有 SKILL.md 链接的函数在代码中存在
- MEMORY.md 所有条目可访问

## Rules

- 只更新与 EDM 验证相关 skill 和 memory
- 不要修改代码文件
- 不要跳过任何步骤
- 更新完成后简要总结改动

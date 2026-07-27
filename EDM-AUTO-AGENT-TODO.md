# EDM Auto Agent TODO

## 方案概要

自动化的 EDM 处理 agent：监听邮箱 → LLM 分析需求 → 自动执行 Skill 链 → 输出结果

## 技术栈

| 项目 | 方案 |
|------|------|
| 监听方式 | EWS HTTP 轮询（参考 `edm_mail_analyzer.ps1`） |
| 运行形式 | 独立 tkinter 桌面小工具 |
| LLM 分析 | litellm → `openai/WanWu/MiniMax-M3`（`litellm_config.yaml`） |
| Skill 执行 | 复用 `edm_process.py` + EDM GUI 导入函数 |
| 结果输出 | `results/agent_*.json` + `Log/agent_*.log` |

## 待开发任务

- [ ] 1. 创建 `edm_agent.py` 主程序
- [ ] 2. 实现 EWS 监听模块（定时轮询 EDM 文件夹）
- [ ] 3. 实现附件下载（保存 .msg + .xlsx 到 Temp）
- [ ] 4. 构建 LLM 分析器（读取邮件内容判断需求类型）
- [ ] 5. 集成 EDM Process Skill 自动执行
- [ ] 6. 集成 Discover XLSX 自动查找
- [ ] 7. 集成 Test List Import（Unimarketing API）
- [ ] 8. 实现结果 JSON + 日志输出
- [ ] 9. 构建 tkinter GUI（状态指示 + 处理记录表 + 日志窗口）
- [ ] 10. 测试运行

## 参考文件

- `edm_mail_analyzer.ps1` — EWS 连接 + 文件夹查找 + 增量轮询
- `edm_process.py` — EDM 处理全链路
- `edm_gui.py` — GUI 参考 + 导入函数
- `email_monitor.py` — win32com 轮询参考
- `litellm_config.yaml` — LLM 模型配置

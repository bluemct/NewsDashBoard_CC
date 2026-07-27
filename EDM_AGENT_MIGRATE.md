# EDM Agent 迁移 + 换电脑测试指南

## 1. 文件清单

从这台电脑拷贝到另一台电脑，只需要 **5 个文件 + 1 个目录**：

| 文件/目录 | 用途 | 路径 |
|-----------|------|------|
| `edm_agent.py` | 主程序 | 项目根目录 |
| `.edm_agent_config.json` | EWS 凭据 + 路径 + 过滤规则 | 项目根目录 |
| `.edm_agent_llm_config.json` | LLM 模型配置 | 项目根目录 |
| `test_filter_and_llm.py` | EWS + 过滤 + LLM 集成测试 | 项目根目录 |
| `test_llm_only.py` | 纯 LLM 测试（不依赖 EWS） | 项目根目录 |
| `.claude/skills/` | EDM 处理 skill（edm_process.py、eml_to_msg.py 等） | `.claude/skills/edm-process/`、`.claude/skills/eml-to-msg/` |

## 2. Python 依赖

另一台电脑安装：
```bash
pip install requests requests-ntlm litellm extract-msg olefile openpyxl
```

## 3. 测试步骤

### Step 1: 先测 LLM（最快，不依赖 EWS）
```bash
python test_llm_only.py
```
正常输出示例：
```
模型:       openai/Qwen3.5-27B
分析方式:   LLM 语义分析
结果:       ✓ edm_process
置信度:     100%
理由:       邮件明确包含SN号码...
SN:         SN-56619
响应时间:   ~6s
```

### Step 2: 测 EWS + 过滤 + LLM（需要网络）
```bash
python test_filter_and_llm.py
```
正常输出：Stage 1 扫描过滤 → Stage 2 LLM 分析

### Step 3: 测 GUI（需要 Outlook 运行）
```bash
python edm_agent.py
```

## 4. 如果 LLM 报错

- 检查 `.edm_agent_llm_config.json` 的 `api_base` 是否能从另一台电脑访问
- 模型名格式必须是 `<provider>/<model>`，如 `openai/Qwen3.5-27B`
- LLM 失败会自动降级为关键词匹配（fallback），测试仍可继续

## 5. 如果 EWS 报错

- 检查 `.edm_agent_config.json` 的 `ews.url` 是否可达
- `domain_user` 和 `password` 是否正确
- EDM 文件夹是否存在

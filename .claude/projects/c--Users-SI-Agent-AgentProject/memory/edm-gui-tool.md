---
name: edm-gui-tool
description: EDM GUI tkinter 应用，双 Tab（Processor / Verify），支持 EDM 处理和 Unimarketing 导入验证
metadata:
  type: project
---

EDM Email Processor GUI 工具：

- **主文件**: `edm_gui.py`，tkinter 应用，PyInstaller 打包为 `EDM Email Processor.exe`
- **输出目录**: `Desktop/EDM/SN-xxxxx/`
- **打包**: `python -m PyInstaller edm_gui.spec`（`-y` 清理旧输出）
- **输出文件夹**: 嵌套 .msg、EDM_template.html、formal_*.csv、test_*.csv、process.log

**双 Tab 界面**:
- **EDM Processor**: 选 .msg + .xlsx → Process → 生成 SN 文件夹 → Import Test/Formal List
- **Verify**: 输入 SN/Filename → Discover → 查找 Formal List → Verify（Email 验证）/ Deep Verify（字段全比）

**核心依赖** (动态 import):
- `edm_process` — extract_sn, replace_span_tokens, save_target_attachment
- `unimarketing_test_list` — API 导入流程
- `verify_list_contacts` — 导入后验证
- `deep_verify_list` — 深验证

**PyInstaller spec**: `edm_gui.spec` — datas 包含 config.json, Tokenmapping.json, xlsx_search_dir.json, verify_list_contacts.py, deep_verify_list.py

See also: [[pyinstaller-always-clean-build]], [[fix-edm-gui-bytes-attachment-anti-hang]], [[edm-gui-exe-import-fix]], [[list-verify-feature]], [[deep-verify-feature]], [[edm-discover-filename-match]], [[edm-process-cleanup-fix]]

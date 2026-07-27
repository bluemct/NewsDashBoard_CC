# EDM Email Processor

## 功能说明

EDM Email Processor 是一款 Windows 桌面工具，用于自动化处理 EDM（Electronic Direct Mail）电子邮件。用户只需提供原始邮件文件（.msg）和联系人列表文件（.xlsx），工具即可完成全部处理流程，生成可用于发送的 EDM 模板和 CSV 数据文件。

### 核心功能

| 步骤 | 功能 | 说明 |
|------|------|------|
| 1 | SN 编号提取 | 从 .msg 邮件主题自动提取 SN 编号（如 SN-56262） |
| 2 | 输出文件夹创建 | 在指定输出目录下自动创建 `SN-xxxxx/` 文件夹 |
| 3 | 联系人数据转换 | 将 .xlsx 转换为 GB18030 编码的 CSV |
| 4 | EDM 模板提取 | 从原始邮件中提取嵌套的 EDM 模板 .msg 文件 |
| 5 | HTML 模板生成 | 通过 Outlook 将 .msg 转为 HTML，插入主题行，替换 Token 占位符 |
| 6 | 正式/测试 CSV 生成 | 生成 `formal_*.csv`（全部数据）和 `test_*.csv`（测试邮箱） |

### 配置文件

工具同级目录下需放置两个配置文件：

| 文件 | 作用 | 格式 |
|------|------|------|
| `config.json` | 测试邮箱地址列表 | `{"test_emails": ["email1", "email2"]}` |
| `Tokenmapping.json` | Token 占位符映射 | `[{"Name": "%%Token1%%", "Value": "${contactToken}"}]` |

---

## 使用说明

### 环境要求

- Windows 10 或以上
- Python 3.10+（命令行使用）
- Outlook 客户端需正常运行且已连接 Exchange（HTML 转换需要）

### 快速开始

1. **启动工具** — 双击运行 `EDM Email Processor.exe`
2. **选择文件**
   - 点击 **Browse...** 选择原始 .msg 邮件文件
   - 点击 **Browse...** 选择联系人 .xlsx 文件
3. **选择输出目录** — 默认为 `桌面\EDM\`，可自定义
4. **配置选项（可选）**
   - 点击 **▶ Expand Config** 展开配置面板
   - **Test Emails** 标签页：编辑测试邮箱地址
   - **Tokenmapping** 标签页：编辑 Token 占位符映射
5. **点击 Process** — 等待处理完成
6. **打开输出文件夹** — 点击 **Open Output Folder** 查看结果

### 输出文件说明

处理完成后，`桌面\EDM\SN-xxxxx/` 目录下生成以下文件：

| 文件 | 说明 |
|------|------|
| `*.msg` | 提取的 EDM 模板 .msg 文件 |
| `EDM_template.html` | 完整的 HTML 邮件模板（含主题行、Token 已替换为 API 占位符） |
| `formal_*.csv` | 正式联系人列表（包含所有行） |
| `test_*.csv` | 测试联系人列表（行数 = config.json 中测试邮箱数量，邮箱列已替换为测试邮箱） |
| `process.log` | 处理过程日志 |

### Token 字段映射

CSV 中的 `Token1`~`Token15` 列，对应 Unimarketing API 字段名：

| CSV 列名 | API 字段名 |
|----------|-----------|
| Token1 | Token |
| Token2 | TokenT |
| Token3 | TokenH |
| Token4 | TokenF |
| Token5 | TokenI |
| Token6 | TokenS |
| Token7 | TokenE |
| Token8 | TokenG |
| Token9 | TokenN |
| Token10 | TokenTEN |
| Token11 | TokenL |
| Token12 | TokenW |
| Token13 | TokenR |
| Token14 | TokenO |
| Token15 | TokenV |

### 注意事项

- **Outlook 必须运行**：HTML 转换依赖 Outlook 的 `HTMLBody` 属性（.msg 文件只存储 RTF，由 Outlook 实时转换为 HTML）
- **config.json 控制测试行数**：`test_emails` 数组中有几个邮箱，`test_*.csv` 就生成几行
- **Tokenmapping.json 为空或不存在**：跳过 Token 替换，保留原始 `%%Token1%%` 等占位符
- **处理过程在后台线程运行**：不会阻塞界面，可在 Log 区域查看实时进度

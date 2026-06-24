# EDM Email Processor GUI — 使用说明

## 功能概述

EDM Email Processor GUI 是一个 Windows 桌面工具，用于一站式处理 EDM 邮件：

1. 从 `.msg` 邮件提取 SN 编号，创建输出文件夹
2. 将 `.xlsx` 转换为 CSV
3. 提取 `.msg` 中的嵌套 `.msg` 附件
4. 将嵌套 `.msg` 转换为 HTML（支持 Token 替换）
5. 生成 formal 和 test 两套 CSV
6. 可将联系名单导入 Unimarketing 系统

## 系统要求

- Windows 10 / Server 2016+
- Outlook 已安装并登录
- Python 3.10+（如使用 .exe 打包版则无需 Python）
- Git for Windows（用于从 GitHub 拉取数据）
- 依赖库：`extract-msg`, `olefile`, `openpyxl`, `pywin32`

## 配置文件

工具启动后会查找以下两个 JSON 配置文件（与 `.exe` 或 `.py` 文件同一目录）：

### config.json — 测试邮件地址

```json
{
  "test_emails": [
    "ma.chuntao@oe.21vianet.com",
    "microsoft.163163@163.com"
  ]
}
```

test CSV 会将这 2 个地址填入 Email 列。

### Tokenmapping.json — Token 名称到值的映射

```json
[
  {
    "Name": "Token1",
    "Value": "替换后的实际值"
  },
  {
    "Name": "Token2",
    "Value": "替换后的实际值"
  }
]
```

转换 HTML 时，HTML 中的 `<span>Token1</span>` 会被替换为 `替换后的实际值`。

## 使用流程

### 第 1 步：选择输入文件

1. 点击 **MSG File** 旁的 "Browse..." 按钮，选择 EDM 请求的 `.msg` 文件
2. 点击 **XLSX File** 旁的 "Browse..." 按钮，选择联系人 Excel 文件

### 第 2 步：选择输出文件夹

默认输出到 `桌面/EDM/` 目录，可点击 "Browse..." 修改。

### 第 3 步：配置（可选）

点击 "▶ Expand Config" 展开配置区域：

- **Test Emails** 标签页：查看/编辑 `config.json` 中的测试邮件地址
- **Tokenmapping** 标签页：查看/编辑 `Tokenmapping.json` 中的 Token 映射

点击 "Edit..." 打开编辑器，修改后点击 "Save" 保存。

### 第 4 步：点击 "Process" 执行处理

处理完成后日志区显示所有步骤，输出文件夹包含：

| 文件 | 说明 |
|------|------|
| `SN-12345.msg` | 嵌套的原始邮件附件 |
| `EDM_template.html` | 转换为 HTML 后的邮件正文（含 Token 替换） |
| `formal_*.csv` | 正式发送联系名单（全部行） |
| `test_*.csv` | 测试联系名单（2 行，使用 config.json 中的测试邮箱） |
| `process.log` | 处理日志 |

点击 **"Open Output Folder"** 打开输出文件夹。

### 第 5 步：导入 Unimarketing 联系名单（可选）

选择 xlsx 文件后，界面下方会出现两个导入按钮：

- **Import Test List** — 将 test CSV 导入 Unimarketing 测试名单
- **Import Formal List** — 将 formal CSV 导入 Unimarketing 正式名单

导入流程：生成 CSV → 调用 Unimarketing API 创建 List → 提交联系人 → 执行导入 → 显示结果。

导入 Formal List 前会有确认提示。

## 常见问题

| 问题 | 解决方法 |
|------|---------|
| 提示"No SN number found" | 确保 .msg 邮件主题或文件名包含 `SN-12345` 格式编号 |
| 提示"Missing dependency extract-msg" | 运行 `pip install extract-msg` |
| 提示"could not connect to Outlook" | 确保 Outlook 已打开并登录 Exchange |
| HTML 没有生成 | 检查 .msg 中是否有 0 收件人的 `.msg` 附件 |
| config.json 找不到 | 点击 Expand Config → Edit 创建默认配置 |

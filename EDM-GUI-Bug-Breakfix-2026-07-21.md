# EDM GUI Bug Breakfix — 2026-07-21

## 问题：RE: 邮件导致 EDM GUI 卡死，无日志输出

### 现象

用户反馈处理一封 `RE:` 开头的回复邮件时，EDM GUI 点击 Process 后界面卡死，Log 区域没有任何错误信息输出。

- **触发文件**: `RE_ _EDM test and distribution_ Incident 795642121 - SN-55247 ...msg`
- **正常邮件**: `_EDM test and distribution_ Incident 795642121 - SN-55247 ...msg`（同 SN，非 RE:）

---

### 根因分析

#### 1. 直接原因：`att.data` 类型差异导致 `AttributeError`

`extract-msg` 对同一个嵌套 .msg 附件有两种返回类型：

| 邮件类型 | `att.data` 类型 | 有 `.exportBytes()`？ |
|----------|----------------|---------------------|
| 正常邮件 | `Message` 对象 | ✅ 有 |
| RE: 回复邮件 | `bytes` 原始数据 | ❌ 无 |

`save_target_attachment()` 假设一定是 Message 对象：

```python
nested = att.data
raw = nested.exportBytes()  # ← bytes 类型直接 AttributeError
```

**commit `2d57431`**: 加类型判断
```python
nested = att.data
if isinstance(nested, bytes):
    raw = nested
else:
    raw = nested.exportBytes()
```

#### 2. 间接原因：异常被后台线程吞掉

即使报错，GUI 也没有显示任何错误信息，因为：

- `_process()` 在 `threading.Thread` 后台运行
- `on_error` 回调中 `messagebox.showerror` 的 `lambda` 存在延迟绑定问题
- `root.after()` 调度失败时无任何 fallback
- 整个 `_process` 没有最外层 try/except 兜底

**commit `2d57431`**: 全面加固
- `ProcessLogger.log()` — `root.after()` 加 `try/except (tk.TclError, RuntimeError)`
- `_process()` 拆分为外层包装 + `_process_inner()`，外层捕获所有未处理异常并写 `[FATAL ERROR] + traceback`
- `on_done` / `on_error` 回调全部包裹，`messagebox` 也保护
- `_convert_msg_to_html()` — `OpenSharedItem`、`HTMLBody` 读取、文件写入各加 try/except + traceback
- `_run_import` 线程 — 最外层 FATAL ERROR 兜底
- `extract_xlsx_filename_from_msg` — 优先从 `htmlBody` 提取 URL（比 `body` text 更可靠）

#### 3. PyInstaller 打包错误：`sys.stdout` 为 None

打包为 windowed exe 后，`sys.stdout` 是 `None`：

```
AttributeError: 'NoneType' object has no attribute 'encoding'
```

**commit `e7fe76b`**: 加 None 守卫
```python
# Before
if sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":

# After
if sys.stdout is not None and sys.stdout.encoding and sys.stdout.encoding.upper() != "UTF-8":
```

---

### 影响范围

| 修改文件 | 影响 EDM GUI？ | 影响 EDM Agent？ |
|----------|:---:|:---:|
| `edm_process.py` (`save_target_attachment`) | ✅ | ❌ |
| `edm_process.py` (`sys.stdout` 守卫) | ✅ exe | ❌ |
| `edm_gui.py` (全面错误日志) | ✅ | ❌ |

**EDM Agent** (`edm_agent_send_email.py`) 完全不引用 `edm_process`，不受影响。

---

### Commit 记录

| Commit | 时间 | 说明 |
|--------|------|------|
| `2d57431` | 2026-07-21 14:57 | handle bytes attachment data, add comprehensive error logging & anti-hang protection |
| `e7fe76b` | 2026-07-21 15:10 | handle sys.stdout None in PyInstaller windowed mode |

### 验证

两封邮件均在修复后验证通过：
- 正常邮件 (14:56:01) — Processing Complete ✓
- RE: 邮件 (14:55:19) — Processing Complete ✓（之前卡死）

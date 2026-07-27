---
name: fix-edm-gui-import-worker-closure
description: 修复 EDM GUI Import 调用 _import_worker 时误用 self. 导致 AttributeError
metadata:
  type: feedback
---

**2026-07-23 修复**: `edm_gui.py` 第 1312 行 `_do_import()` 中调用 `self._import_worker(...)` 报错

```
AttributeError: 'EDMGUI' object has no attribute '_import_worker'
```

**原因**: `_import_worker` 是 `_run_import()` 方法内定义的局部函数（line 1319），不是类方法。
**修复**: `self._import_worker(...)` → `_import_worker(...)`，通过闭包访问即可。

See also: [[edm-gui-tool]]

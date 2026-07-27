# EDM Dashboard 部署文档

## 适用场景

在另一台 Windows 电脑上部署 EDM Dashboard 服务，供域内用户通过浏览器访问。

## 目标电脑要求

- Windows 10 / Server 2016+
- 加入 `bj-oe.21vianet.com` 域
- Python 3.10+（[下载地址](https://www.python.org/downloads/)）
- Git for Windows（[下载地址](https://git-scm.com/download/win)）

## 安装 Python

1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.13 LTS 安装包
3. 安装时勾选 **"Add Python to PATH"**（重要！）
4. 验证安装：

```cmd
python --version
```

输出类似 `Python 3.13.0` 即安装成功。

## 安装 pywin32

```cmd
pip install pywin32
```

## 复制文件到目标电脑

需要复制以下内容到目标电脑（假设目标路径 `D:\EDM_Dashboard\`）：

```
D:\EDM_Dashboard\
├── edm_dashboard.py              ← 主程序（从 .claude\skills\edm-dashboard\edm_dashboard.py）
├── edmmailanalyzer.json          ← 本地数据文件
└── run_dashboard.vbs             ← 后台启动脚本
```

> **注意**：`run_dashboard.vbs` 中的路径已配置为 `D:\EDM_Dashboard\`。

## 启动服务

### 方式一：双击 VBS 脚本（推荐，后台运行无黑窗口）

1. 编辑 `run_dashboard.vbs` 中的路径为实际路径
2. 双击运行 `run_dashboard.vbs`
3. 浏览器访问 `http://localhost:8765`

### 方式二：命令行运行

```cmd
cd D:\EDM_Dashboard
python -X utf8 edm_dashboard.py --port 8765 --json-file edmmailanalyzer.json
```

> **停止服务**：Ctrl+C 关闭命令行窗口即可。

## 配置 Windows 防火墙

如需让其他电脑访问，需开放端口：

```powershell
# 以管理员身份运行 PowerShell
New-NetFirewallRule -DisplayName "EDM Dashboard" -Direction Inbound -LocalPort 8765 -Protocol TCP -Action Allow
```

然后其他电脑浏览器访问 `http://<目标电脑IP>:8765`

## 配置 Windows 计划任务（开机自动启动）

如需开机自动启动服务：

1. 打开"任务计划程序"（Win+R → `taskschd.msc`）
2. 点击"创建任务"
3. 常规选项卡：
   - 名称：`EDM Dashboard`
   - 勾选"不管用户是否登录都要运行"
   - 勾选"使用最高权限运行"
4. 触发器选项卡：
   - 新建 → 启动时
5. 操作选项卡：
   - 新建 → 启动程序
   - 程序：`C:\Python313\python.exe`（根据实际安装路径修改）
   - 参数：`-X utf8 D:\EDM_Dashboard\edm_dashboard.py --port 8765 --json-file D:\EDM_Dashboard\edmmailanalyzer.json`
   - 起始于：`D:\EDM_Dashboard\`
6. 确定保存

## 更新文件

当主代码有更新时，只需：

1. 将最新的 `edm_dashboard.py` 复制覆盖到 `D:\EDM_Dashboard\`
2. 双击 `run_dashboard.vbs`（先通过任务管理器结束旧的 python.exe）

## 登录使用

1. 浏览器打开 `http://localhost:8765`
2. 使用 `bj-oe.21vianet.com` 域账号登录
3. 输入域用户名（不含域名）和密码
4. 登录有效期 1 小时，到期后刷新数据页会自动弹出登录框

## 故障排查

| 问题 | 解决方法 |
|------|---------|
| python 命令找不到 | Python 安装时未勾选 Add to PATH，重新安装或手动添加到系统环境变量 |
| pywin32 模块找不到 | 运行 `pip install pywin32` |
| 页面空白 / 乱码 | 确保使用 `python -X utf8` 运行，不是直接 `python` |
| 手动刷新无数据 | 检查 git 能否访问 GitHub：`git clone --depth 1 https://github.com/bluemct/docs.git` |
| 端口被占用 | 换端口：`python -X utf8 edm_dashboard.py --port 9999` |
| 无法从其他电脑访问 | 检查 Windows 防火墙是否开放端口，或暂时关闭防火墙测试 |
| VBS 脚本无响应 | 打开任务管理器，查看是否有 python.exe 进程；如有说明已启动 |

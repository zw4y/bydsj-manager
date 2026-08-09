# 捕鱼大世界资源读取工具（快速打通轮）实施计划

> **For agentic workers:** 本轮采用 inline 执行，任务按顺序推进，每个任务以可运行结果收尾。

**Goal:** 打通「自动启动模拟器与游戏 → Frida 读取 11 个道具数量 → 桌面端展示」的完整链路，交付一个可运行 exe。

**Architecture:** 四层：控制层（ldconsole/adb）、采集层（FridaCollector，只读 JS）、数据层（models/config/CSV/日志）、界面层（PySide6 表格）。

**Tech Stack:** Python 3.12.4、frida、PySide6、ldconsole/adb（E:\leidian\LDPlayer9）、PyInstaller。

## Global Constraints

- 只读游戏内存，禁止修改/写入内存。
- 不提供隐藏或绕过反外挂检测的功能。
- 游戏包名 `com.shiyi.by3d`，模拟器实例名「雷电模拟器」。
- 11 个道具固定清单：神灯、锁定、冰冻、狂暴、号角、绿灵石、金刚石、紫晶石、血精石、原石精华、战魂自选礼盒。
- 单账号；最终交付物为 Windows exe。

## 文件结构

- `.venv/`：Python 虚拟环境
- `requirements.txt`：依赖清单
- `config.json`：运行配置（含 11 道具清单）
- `src/main.py`：入口 + 桌面界面
- `src/models.py`：Item / InventoryData / Config
- `src/ldplayer_controller.py`：模拟器控制层
- `src/frida_collector.py`：Frida 采集层
- `src/logger.py`：日志
- `scripts/probe.py`：内存探索辅助脚本
- `scripts/scan_names.js`：Frida 内存扫描脚本
- `dist/`：打包输出目录

## Task 1: 环境准备与 frida-server 部署

1. 创建 `.venv`，安装 `frida`、`frida-tools`。
2. 查询 `frida.__version__`，从 GitHub 下载匹配版本的 `frida-server-<ver>-android-x86_64.xz`。
3. 解压，`adb push` 到 `/data/local/tmp/frida-server`，`chmod 755`。
4. 以 root 启动 frida-server。
5. 验证 `frida-ps -U` 能看到 `com.shiyi.by3d`。

产出：可附加游戏进程的 frida 环境。

## Task 2: 内存定位 11 个道具

1. `scripts/scan_names.js`：遍历可读内存，搜索 11 个道具名称（UTF-8 与 UTF-16），输出命中地址与所在模块。
2. `scripts/probe.py`：附加进程、枚举模块（重点 `libil2cpp.so`、`libxlua.so`）、执行扫描、保存 `hits.json`。
3. 动态对比：用户消耗/获得某道具前后，对命中地址附近内存 dump 并 diff，确认数量字段。
4. 产出 `item_map.json`：`name -> {id, 地址模板}`。

验收：至少大部分道具能稳定读到数量。

## Task 3: 采集与控制层

1. `src/models.py`：`Item`、`InventoryData`、`Config` 数据模型。
2. `src/ldplayer_controller.py`：路径校验、列实例、启动实例、等待启动完成、拉起游戏、等待进程。
3. `src/frida_collector.py`：确保 frida-server 运行、附加进程、执行 JS、解析为 `InventoryData`。
4. 命令行自测：一次调用返回 11 个道具的数量 JSON。

验收：脚本能独立完成「启动 → 读取 → 输出 JSON」。

## Task 4: 桌面端与打包

1. `src/main.py`：PySide6 表格（名称/数量）、按钮（启动并读取/刷新/导出 CSV）、状态栏。
2. 运行日志写入 `logs/`。
3. PyInstaller `--onefile` 打包，干净目录双击验证。

验收：双击 exe → 自动完成启动与读取 → 表格显示 11 个道具数量。

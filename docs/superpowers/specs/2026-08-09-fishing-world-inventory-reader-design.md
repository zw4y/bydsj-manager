# 捕鱼大世界仓库/背包资源读取工具 —— 设计文档

- 日期：2026-08-09
- 状态：待用户审阅
- 版本：v0.1

## 1. 背景与目标

用户在 Windows 上通过雷电模拟器玩《捕鱼大世界》（包名 `com.shiyi.by3d`），需要一个桌面可运行的 exe 工具：

- 无需手动打开模拟器或游戏，点击按钮即可自动完成「启动模拟器 → 启动游戏 → 等待就绪 → 读取数据 → 展示」。
- 读取用户自己账号仓库/背包中 11 种核心道具的名称与数量。
- 第一版只支持单账号，但架构上为将来多账号管理平台预留扩展点。

## 2. 范围

### MVP 包含

- Windows 可运行 exe（PyInstaller 打包，Python + PySide6）。
- 自动启动指定雷电模拟器实例并拉起游戏。
- 使用 Frida 读取游戏进程内存/运行时数据（唯一采集方式）。
- 展示 11 种道具：神灯、锁定、冰冻、狂暴、号角、绿灵石、金刚石、紫晶石、血精石、原石精华、战魂自选礼盒。
- 道具行显示：名称、数量；单项读取失败时显示「未读取到」。
- 功能：启动并读取、手动刷新、导出 CSV、运行日志。

### 本期明确不做

- 多账号管理界面与多实例并行读取。
- 详细的界面美化与前端设计。
- 网络抓包解析、OCR/屏幕识别。
- 修改游戏内存、自动化操作游戏内容。
- 隐藏或绕过反外挂检测的任何功能。

## 3. 环境现状（已勘察确认）

| 项目 | 值 |
| --- | --- |
| 模拟器 | 雷电模拟器 9，v9.2.6.0 |
| 安装路径 | `E:\leidian\LDPlayer9` |
| adb | `E:\leidian\LDPlayer9\adb.exe`，设备 `emulator-5554` |
| Android 版本 | 9（API 28），x86_64 |
| Root | 可用（`su -c id` 返回 uid=0） |
| 游戏包名 | `com.shiyi.by3d` v6.02.10 |
| 游戏引擎 | Unity IL2CPP + xLua（原生库含 `libil2cpp.so`、`libxlua.so`） |
| 安全 SDK | `libmsaoaidsec.so`（阿里移动安全），存在检测/风控风险 |
| 当前模拟器实例名 | `雷电模拟器` |

## 4. 技术选型

- 语言：Python 3.11+。
- 桌面界面：PySide6。
- 内存采集：frida（主机端 Python 绑定 + 模拟器内 frida-server）。
- 模拟器控制：雷电官方 `ldconsole.exe` 与 `adb.exe`。
- 打包：PyInstaller 生成单文件 exe。
- 配置：`config.json`；导出：CSV；日志：本地 logs 目录。

## 5. 总体架构（四层）

### 5.1 控制层：LDPlayerController

- 职责：校验工具路径、列出实例、启动实例、拉起游戏、等待系统/游戏就绪。
- 对外接口：`start_and_wait_game() -> GameSession`。
- 将来多账号：一个账号配置对应一个模拟器实例，由本层统一调度。

### 5.2 采集层：FridaCollector（唯一实现）

- 职责：准备/启动 frida-server、附加游戏进程、执行只读 JS 脚本、解析道具数据。
- 对外接口：`read_inventory(session) -> InventoryData`。
- 采集脚本只读内存与运行时数据，不修改任何游戏数据。

### 5.3 数据层

- 数据模型：`Item`、`InventoryData`。
- 职责：加载/保存配置、解析采集结果、导出 CSV、写日志。

### 5.4 界面层：MainWindow

- 状态栏：模拟器状态、游戏状态、采集状态。
- 按钮：启动并读取、刷新、导出 CSV。
- 表格：道具名称、数量。

## 6. 数据模型

```python
@dataclass
class Item:
    id: str          # 游戏内道具 ID（逆向确认前为占位符）
    name: str        # 道具名称（11 种固定清单之一）
    count: int       # 数量
    status: str      # "ok" | "missing"

@dataclass
class InventoryData:
    account_name: str
    collected_at: str
    items: list[Item]
```

`config.json` 结构：

```json
{
  "ldconsole_path": "E:\\leidian\\LDPlayer9\\ldconsole.exe",
  "adb_path": "E:\\leidian\\LDPlayer9\\adb.exe",
  "instance_name": "雷电模拟器",
  "package_name": "com.shiyi.by3d",
  "collector": "frida",
  "timeouts": {
    "boot_seconds": 120,
    "process_seconds": 120,
    "attach_seconds": 60
  },
  "items": [
    { "id": "TBD", "name": "神灯" },
    { "id": "TBD", "name": "锁定" },
    { "id": "TBD", "name": "冰冻" },
    { "id": "TBD", "name": "狂暴" },
    { "id": "TBD", "name": "号角" },
    { "id": "TBD", "name": "绿灵石" },
    { "id": "TBD", "name": "金刚石" },
    { "id": "TBD", "name": "紫晶石" },
    { "id": "TBD", "name": "血精石" },
    { "id": "TBD", "name": "原石精华" },
    { "id": "TBD", "name": "战魂自选礼盒" }
  ]
}
```

说明：`items[].id` 在逆向定位完成后由工具自动回填并保存，不是遗留的待办项。

## 7. 数据流

用户点击「启动并读取」：

1. 控制层校验配置与 `ldconsole/adb` 路径。
2. `ldconsole launch` 启动指定实例。
3. adb 轮询 `sys.boot_completed=1`（超时 120 秒）。
4. `ldconsole runapp` 启动 `com.shiyi.by3d`。
5. 轮询游戏进程出现（超时 120 秒）；若需手动登录，状态栏提示「等待登录」，登录后自动继续。
6. FridaCollector 附加进程，执行只读 JS 脚本读取道具数据。
7. 解析 JSON 生成 `InventoryData`。
8. 界面刷新表格，状态栏显示结果；用户可导出 CSV。

## 8. 采集实现要点

- 将匹配 x86_64 的 frida-server 放入模拟器 `/data/local/tmp`，以 root 启动。
- 通过 adb 建立连接（`frida` 支持 adb 设备）。
- 第一阶段逆向定位：
  - 在游戏内存中搜索 11 个道具名称对应的字符串/道具 ID；
  - 通过「使用/获得某道具前后内存差异对比」确认数量字段位置；
  - 将确认后的 ID 回填 `config.json`。
- 采集脚本输出统一 JSON：`{ "items": [{"id", "name", "count"}] }`。
- 全程只读：不写入游戏内存、不调用修改类接口。

## 9. 错误处理

| 场景 | 行为 |
| --- | --- |
| ldconsole/adb 路径不存在 | 启动前校验，弹窗提示 |
| 模拟器实例不存在 | 列出可用实例并提示 |
| 系统启动超时 | 提示超时，允许重试 |
| 游戏未安装 | 提示需在模拟器内安装 `com.shiyi.by3d` |
| 游戏进程未出现 | 提示启动失败或需要手动登录 |
| frida-server 未运行/附加失败 | 提示重新初始化采集环境 |
| 安全 SDK 检测导致游戏退出 | 状态栏警告并写日志；不做对抗 |
| 单个道具读取失败 | 该行显示「未读取到」，其余正常 |

每次运行写入 `logs/yyyyMMdd_HHmmss.log`。

## 10. 测试与验收

1. 环境验证：`su` 可用、frida-server 正常启动、可附加游戏进程并读到一次数据。
2. 端到端测试：点击「启动并读取」，表格 11 个道具数量与游戏背包界面一致。
3. 变化测试：在游戏中获得/消耗某道具后刷新，数量正确变化。
4. 打包测试：PyInstaller 产物在干净目录双击运行通过。

验收标准：双击 exe → 自动完成启动与读取 → 表格正确显示 11 个道具的数量。

## 11. 风险与合规

- 工具仅读取用户自己账号的数据，不涉及他人数据。
- 游戏含阿里移动安全 SDK，Frida 注入可能被检测，存在踢下线/封号风险，由用户自担。
- 不提供隐藏、绕过或对抗安全检测的功能。
- 游戏版本更新可能导致采集逻辑失效，需要维护脚本。

## 12. 后续扩展（本期不实现）

- 多账号管理：账号 ↔ 模拟器实例映射，批量启动与读取。
- 道具清单扩展：从 11 种扩展到全部仓库/背包道具。
- 历史数据统计、数量变化告警。

## 13. 里程碑

- M0 环境验证：部署 frida-server、附加游戏、定位 11 个道具 ID 与数量字段。
- M1 采集模块：FridaCollector、数据模型、JSON 解析。
- M2 桌面端整合：控制层、界面、导出、日志、错误处理。
- M3 打包与验收：PyInstaller 打包、端到端测试、交付 exe。

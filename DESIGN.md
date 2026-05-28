# 金铲铲智能助手 — 设计文档

## 项目概述

金铲铲之战（国服手游）智能助手，通过 ADB 连接安卓模拟器，截图识别游戏画面，自动执行游戏操作。插件化架构，支持全自动/半自动模式切换。

## 技术栈

| 模块 | 技术选型 | 说明 |
|------|---------|------|
| 语言 | Python | 生态丰富，CV/OCR 库成熟 |
| UI 框架 | CustomTkinter | 现代化 Tkinter，美观轻量 |
| ADB 通信 | `adbutils` | 设备连接与控制 |
| 文字识别 | PaddleOCR | 中文识别精度优 |
| 图像处理 | OpenCV | 模板匹配、图像预处理 |
| 轻量模型 | ONNX Runtime | 推理复杂场景识别模型 |
| 数据请求 | `httpx` | 异步 HTTP，在线数据更新 |
| 配置管理 | `pyyaml` | YAML 配置文件 |
| 事件总线 | 自研 | 发布/订阅模式 |
| 打包发布 | `PyInstaller` | 打包为 exe |

## 架构设计：插件化方案

```
┌─────────────────────────────────────────────┐
│              CustomTkinter UI               │
├─────────────────────────────────────────────┤
│               核心框架 (Core)                │
│  ┌───────────┬──────────┬───────────────┐   │
│  │ 插件管理器  │ 事件总线  │   配置中心    │   │
│  │ PluginMgr │ EventBus │  ConfigMgr   │   │
│  └───────────┴──────────┴───────────────┘   │
├────┬────┬─────┬────┬─────┬─────┬────────────┤
│ADB │截图│ 图像 │阵容│ 决策 │ 操作 │  牌库     │
│连接│采集│ 识别 │分析│ 引擎 │ 执行 │  预测     │
│    │    │     │    │     │     │           │
└────┴────┴─────┴────┴─────┴─────┴────────────┘
```

### 事件流

```
ADB插件: 发布 "screenshot_ready"
  → 图像识别: 处理，发布 "game_state_updated"
    → 阵容分析: 计算，发布 "best_comp_found"
      → 决策引擎: 决策，发布 "action_required"
        → 操作执行: 执行 ADB 操作
```

## 插件设计

### 插件接口规范

每个插件实现统一接口：
- `init()` — 初始化
- `start()` — 启动
- `stop()` — 停止
- `get_config_schema()` — 返回配置项定义

### 各插件职责

#### 1. ADB 连接插件
- 自动检测已连接的模拟器（MuMu、雷电、夜神等）
- 支持手动输入 ADB 地址连接
- 心跳检测连接状态，断线自动重连
- 输出事件：`device_connected`、`device_disconnected`

#### 2. 截图采集插件
- 周期性截图（可配置频率，默认 500ms）
- 支持全屏截图和区域截图（减少处理开销）
- 截图缓存队列，避免阻塞
- 输出事件：`screenshot_ready`（携带图像数据）

#### 3. 图像识别插件
- **文字识别**：PaddleOCR 识别费用、等级、金币等数字文字
- **图标识别**：模板匹配识别弈子头像、装备图标
- **棋盘状态**：识别棋盘格子上的弈子位置
- 输出事件：`game_state_updated`（携带结构化游戏状态）

#### 4. 阵容分析插件
- 根据当前弈子池和已有弈子，计算最优阵容推荐
- 内置版本数据（羁绊、费用、推荐阵容）
- 支持在线拉取最新数据热更新
- 输出事件：`best_comp_found`（携带推荐阵容和优先级）

#### 5. 决策引擎插件
- 综合游戏状态、阵容推荐、经济情况做出决策
- 决策类型：买什么牌、站位调整、升级时机、装备分配
- 半自动模式下发给 UI 确认，全自动模式直接执行
- 输出事件：`action_required`（携带具体操作指令）

#### 6. 操作执行插件
- 接收操作指令，转化为 ADB 点击/滑动坐标
- 操作队列，避免冲突
- 坐标自适应（不同模拟器分辨率自动校准）
- 输出事件：`action_executed`（携带执行结果）

#### 7. 牌库预测插件
- 记录已出场/已售出的卡牌
- 结合 OCR 识别其他7家玩家的棋盘
- 概率模型推算目标弈子的出现概率
- 输出事件：`pool_prediction_updated`

## UI 设计

```
┌─────────────────────────────────────────────────────┐
│  金铲铲智能助手                        ─  □  ×      │
├──────────────┬──────────────────────────────────────┤
│              │                                      │
│  ◉ 实时状态   │    截图预览 / 游戏画面识别结果         │
│              │                                      │
│  ◎ 阵容推荐   │    ┌─────────────────────────────┐   │
│              │    │                             │   │
│  ◎ 站位管理   │    │      棋盘可视化区域          │   │
│              │    │                             │   │
│  ◎ 牌库预测   │    └─────────────────────────────┘   │
│              │                                      │
│  ◎ 操作日志   │    操作面板：                         │
│              │    [半自动] [全自动]  操作开关列表       │
│  ──────────  │                                      │
│              │    ┌─────────────────────────────┐   │
│  ⚙ 设置      │    │ 操作日志实时滚动显示          │   │
│              │    └─────────────────────────────┘   │
│              │                                      │
└──────────────┴──────────────────────────────────────┘
```

**页面说明：**
- **左侧导航栏**：切换不同功能页面
- **实时状态页**：当前游戏阶段、金币、等级、血量、连接状态
- **阵容推荐页**：当前推荐阵容列表，弈子详情，转型建议
- **站位管理页**：棋盘可视化，当前站位 vs 推荐站位对比
- **牌库预测页**：目标弈子出现概率、剩余数量、购买建议
- **操作日志页**：所有自动操作的时间线记录
- **设置页**：ADB 配置、自动化开关、模拟器分辨率校准

## 项目目录结构

```
jinchanchan/
├── main.py                    # 程序入口
├── config.yaml                # 全局配置
├── requirements.txt           # 依赖清单
│
├── core/                      # 核心框架
│   ├── __init__.py
│   ├── plugin_manager.py      # 插件管理器
│   ├── event_bus.py           # 事件总线
│   ├── config_manager.py      # 配置中心
│   └── base_plugin.py         # 插件基类
│
├── plugins/                   # 插件目录
│   ├── __init__.py
│   ├── adb_connector/         # ADB 连接插件
│   ├── screenshot/            # 截图采集插件
│   ├── recognizer/            # 图像识别插件
│   ├── comp_analyzer/         # 阵容分析插件
│   ├── decision_engine/       # 决策引擎插件
│   ├── action_executor/       # 操作执行插件
│   └── pool_predictor/        # 牌库预测插件
│
├── data/
│   ├── current_season         # 配置：当前赛季标识
│   ├── s14/                   # 赛季14
│   │   ├── champions.json
│   │   ├── traits.json
│   │   ├── items.json
│   │   ├── comps.json
│   │   └── pool.json
│   └── ...
│
├── templates/
│   ├── current_season         # 配置：当前赛季标识
│   ├── s14/
│   │   ├── champions/         # 弈子头像模板
│   │   ├── items/             # 装备图标模板
│   │   ├── ui/                # UI 元素模板
│   │   └── board/             # 棋盘布局模板
│   └── ...
│
├── models/
│   ├── s14/
│   └── ...
│
└── ui/
    ├── __init__.py
    ├── app.py                 # 主窗口
    ├── pages/                 # 各页面组件
    └── components/            # 复用组件
```

## 决策日志

| 决策项 | 决定 | 备选方案 | 理由 |
|--------|------|---------|------|
| 语言 | Python | TS/C# | 生态丰富，CV/OCR 库成熟 |
| UI | CustomTkinter | PyQt/Tkinter | 美观轻量，MVP 够用 |
| 架构 | 插件化方案C | 单体/前后端分离 | 高度可扩展，长期维护友好 |
| 识别方案 | 混合（OCR+模板+模型） | 纯OCR/纯模型 | 兼顾效率与精度 |
| 数据源 | 本地+在线更新 | 纯本地/纯在线 | 稳定性与时效性兼顾 |
| 自动化模式 | 可切换（半自动默认） | 全自动/纯手动 | 灵活且安全 |
| 文字识别 | PaddleOCR | EasyOCR | 中文识别更优 |
| 开发节奏 | MVP 先行 | 一步到位 | 快速验证核心链路 |
| 数据存储 | 按赛季分目录 | 统一存储 | 赛季更新隔离，旧数据可追溯 |

## MVP 范围

MVP 目标：跑通"截图→识别→决策→操作"核心链路。

**包含：**
1. 核心框架（插件管理器 + 事件总线 + 配置中心）
2. ADB 连接插件（连接模拟器 + 心跳检测）
3. 截图采集插件（周期截图）
4. 图像识别插件 MVP（识别商店弈子 + 金币等级）
5. 决策引擎 MVP（自动购买目标弈子）
6. 操作执行 MVP（点击商店购买）
7. 基础 UI（连接状态 + 截图预览 + 操作日志 + 模式切换）

**不包含（后续迭代）：**
- 阵容分析推荐
- 动态站位调整
- 牌库预测
- 在线数据热更新
- 装备识别与分配
- 选秀自动化

## 模拟器连接设置页设计

### 配置数据结构

`config.yaml` 中 `adb` 部分改为 profiles 数组：

```yaml
adb:
  profiles:
    - name: "MuMu 本机"
      emulator: "mumu"
      host: "127.0.0.1"
      port: 7555
      device_serial: null
  active_profile: "MuMu 本机"
```

预设模拟器默认端口：
- MuMu: 127.0.0.1:7555
- 雷电: 127.0.0.1:5555
- 夜神: 127.0.0.1:62001

### UI 布局

```
┌─────────────────────────────────────────────┐
│  模拟器连接配置                               │
│                                             │
│  配置方案: [MuMu 本机 ▾]  [新建] [删除]       │
│                                             │
│  名称:     [MuMu 本机          ]             │
│  模拟器:   [MuMu (默认7555)   ▾]             │
│  ADB地址:  [127.0.0.1         ]             │
│  ADB端口:  [7555              ]             │
│  设备序列: [                  ] (留空自动检测) │
│                                             │
│  [测试连接]   状态: ● 已连接 - MuMu Player    │
│               分辨率: 1280x720               │
│               ADB版本: 1.0.41               │
│               延迟: 12ms                    │
│                                             │
│  [保存并应用]                                │
└─────────────────────────────────────────────┘
```

### 交互逻辑

1. 下拉框切换配置 → 自动填充表单字段
2. 选择模拟器预设 → 自动填充默认端口
3. 测试连接 → 调用 ADB 插件测试，显示诊断信息（型号、分辨率、ADB 版本、延迟）
4. 保存并应用 → 写入 config.yaml，断开旧连接，用新配置重连
5. 新建 → 弹出名称输入框，创建空白配置
6. 删除 → 确认后删除当前选中配置

### 代码变更

| 文件 | 变更 |
|------|------|
| `config.yaml` | adb 结构改为 profiles 数组 |
| `core/config_manager.py` | 新增 `get_active_adb_config()` 方法 |
| `plugins/adb_connector/plugin.py` | 新增 `test_connection()` 返回诊断信息，支持热重连 |
| `ui/pages/settings_page.py` | 新增设置页 |
| `ui/app.py` | 侧边栏增加"设置"导航项 |

### 决策日志补充

| 决策项 | 决定 | 备选方案 | 理由 |
|--------|------|---------|------|
| 配置管理 | 多套 profiles + 下拉切换 | 单套配置/同时多连 | 灵活切换，MVP 够用 |
| 模拟器预设 | MuMu/雷电/夜神 | 全覆盖/无预设 | 覆盖主流，减少手动输入 |
| 连接测试 | 详细诊断信息 | 简单状态/无测试 | 便于排查连接问题 |

## 调试面板设计

### 概述

为开发者自用构建一个调试面板，集成到主应用侧边栏，支持按模块独立调试。核心能力：事件流监控、插件状态检查、事件模拟/注入。

### 架构

```
core/
  debug_event_bus.py    # DebugEventBus，继承 EventBus，拦截所有事件
  debug_manager.py      # DebugManager，聚合调试数据，供 UI 消费

ui/pages/
  debug_page.py         # 调试面板 UI

plugins/<name>/plugin.py  # 各插件新增可选的 get_debug_info() 方法
```

**核心流程：**
1. `main.py` 根据 `config.yaml` 中 `debug.enabled` 决定使用 `DebugEventBus` 还是原版 `EventBus`
2. `DebugEventBus` 在 `emit()` 时自动记录事件数据到环形缓冲区（500条上限）
3. `DebugEventBus` 在 `on()` 时记录事件订阅关系
4. `DebugManager` 聚合事件日志、插件状态、订阅关系，提供查询接口
5. `DebugPage` UI 从 `DebugManager` 读取数据，轮询间隔 200ms

### DebugEventBus

```python
class DebugEventBus(EventBus):
    def __init__(self, max_events=500):
        super().__init__()
        self._event_log = deque(maxlen=max_events)  # 环形缓冲区
        self._subscription_map = {}  # {event: [handler_names]}
        self._enabled = True

    def on(self, event, handler):
        # 记录订阅关系后调用 super().on()
        pass

    def emit(self, event, data=None):
        if self._enabled:
            self._record_event(event, data)
        super().emit(event, data)

    # 查询接口
    def get_event_log(self, event_filter=None, limit=100) -> list
    def get_subscription_map(self) -> dict
    def clear_log(self)
    def set_enabled(self, enabled: bool)
```

**事件记录格式：**
- `timestamp` — 精确到毫秒
- `event_name` — 事件名称
- `data_summary` — 数据摘要（截断 200 字符，避免大对象如图片数据）
- `handler_count` — 处理该事件的 handler 数量
- `source` — 调用 emit 的模块名（从调用栈提取）

**性能保障：**
- 环形缓冲区自动丢弃旧数据，内存可控
- data_summary 只取 repr() 前 200 字符，不深拷贝原始数据
- UI 轮询 200ms 读取，非实时推送，不耦合调试逻辑和 UI 线程
- deque 操作需加锁（emit 可能从心跳线程、截图线程等多线程调用）

### 插件状态暴露

BasePlugin 新增可选方法：

```python
def get_debug_info(self) -> dict:
    """返回插件内部运行时状态，子类可覆写。默认返回空字典。"""
    return {}
```

各插件预期暴露内容：

| 插件 | get_debug_info 内容 |
|---|---|
| `adb_connector` | 当前设备信息、心跳状态、最后连接时间、重连次数 |
| `screenshot` | 最后截图时间、截图尺寸、黑帧计数、当前间隔 |
| `recognizer` | 最后识别结果缓存（gold/level/shop）、debug 图片路径 |
| `decision_engine` | 当前目标阵容、决策队列、最后决策详情 |
| `action_executor` | 待执行动作队列、最后执行结果、执行耗时 |

### DebugPage UI 布局

```
┌─────────────────────────────────────────────────────┐
│ [调试面板]  [开启监控 ☐]  [清空日志]  [刷新]         │
├──────────┬──────────────────────┬───────────────────┤
│ 插件列表  │   事件流 / 状态 选项卡  │   详情/模拟面板    │
│          │                      │                   │
│ ▸ adb    │ ┌──────────────────┐ │ ┌───────────────┐ │
│   screen │ │ 事件流  │ 状态   │ │ │ 事件详情       │ │
│   recog  │ ├──────────────────┤ │ │               │ │
│   decisi │ │ 10:23:01.123     │ │ │ event: xxx    │ │
│   action │ │ screenshot_ready │ │ │ data: {...}   │ │
│          │ │ [screenshot]     │ │ │ handlers: 2   │ │
│          │ │                  │ │ └───────────────┘ │
│          │ │ 10:23:01.150     │ │                   │
│          │ │ game_state_update│ │ ┌───────────────┐ │
│          │ │ [recognizer]     │ │ │ 事件模拟       │ │
│          │ │                  │ │ │ 事件类型: [▼]  │ │
│          │ │ 10:23:01.200     │ │ │ 数据: [JSON ] │ │
│          │ │ action_required  │ │ │ [发送事件]    │ │
│          │ │ [decision_eng]   │ │ └───────────────┘ │
│          │ └──────────────────┘ │                   │
└──────────┴──────────────────────┴───────────────────┘
```

**左侧 — 插件列表：**
- 列出所有已注册插件，显示运行状态指示灯（绿/红）
- 点击插件名 → 右侧切换到该插件状态视图

**中间 — 选项卡区域：**
- **事件流**：表格视图（时间 | 事件名 | 来源 | 数据摘要 | handler数），新事件自动追加，可暂停滚动，按事件名过滤
- **插件状态**（点击左侧插件后显示）：运行状态、事件订阅列表、配置参数、内部状态

**右侧 — 详情/模拟面板：**
- **事件详情**（点击事件流条目）：完整数据（格式化 JSON）、handler 列表
- **事件模拟**（固定底部）：事件类型下拉框、JSON 数据输入、发送按钮

### 集成方式

```python
# main.py
if config.get("debug", {}).get("enabled", False):
    event_bus = DebugEventBus()
    debug_manager = DebugManager(event_bus)
else:
    event_bus = EventBus()
    debug_manager = None

# 创建 UI 时传入 debug_manager
app = App(plugin_mgr, event_bus, config_mgr, debug_manager)
```

```yaml
# config.yaml 新增
debug:
  enabled: false  # 默认关闭
```

侧边栏仅当 `debug_manager` 不为 None 时显示"调试"按钮。

### 决策日志

| # | 决策 | 备选方案 | 理由 |
|---|---|---|---|
| 1 | DebugEventBus 继承 EventBus | 包装/代理模式 | 继承更简单，super() 直接复用原逻辑 |
| 2 | 环形缓冲区 500 条 | 无限增长 / 文件日志 | 500 条足够回溯近期问题，内存可控 |
| 3 | UI 轮询 200ms | EventBus 推送更新 | 推送会耦合调试逻辑和 UI 线程 |
| 4 | data_summary 截断 200 字符 | 完整记录 | screenshot_ready 含图片数据，必须截断 |
| 5 | 调试开关在 config.yaml | 命令行参数 | 与现有配置体系一致 |
| 6 | get_debug_info 可选实现 | 强制实现 | 避免给空插件增加负担 |

### 已知风险

1. **高频事件性能** — `screenshot_ready` 每秒触发一次（含图片数据），记录时必须截断摘要
2. **线程安全** — EventBus emit 可能从多线程调用，`_event_log` 的 deque 操作需加锁
3. **事件名动态性** — 部分事件运行时才出现，事件模拟的下拉列表需动态更新

### 代码变更清单

| 文件 | 变更 |
|------|------|
| `config.yaml` | 新增 `debug.enabled` 字段 |
| `core/debug_event_bus.py` | 新建，DebugEventBus 类 |
| `core/debug_manager.py` | 新建，DebugManager 类 |
| `core/base_plugin.py` | 新增 `get_debug_info()` 可选方法 |
| `ui/pages/debug_page.py` | 新建，调试面板 UI |
| `ui/app.py` | 侧边栏新增调试按钮，传入 debug_manager |
| `main.py` | 根据配置选择 EventBus 类型，创建 debug_manager |
| 各插件 plugin.py | 可选：覆写 `get_debug_info()` |

## 非功能性假设

- 运行环境：Windows 10/11
- 模拟器已安装并可运行金铲铲之战
- MVP 阶段优先支持 MuMu 模拟器
- 截图识别延迟容忍度：< 1 秒
- 配置文件为本地 YAML，不涉及多用户

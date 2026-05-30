# 棋局态势面板优化计划

## 目标

1. **战斗盘面和备战席宽度与商店对齐** — 改为响应式 grid 布局，填充可用宽度
2. **左侧显示当前装备** — 在棋盘左侧新增装备栏（UI 占位）
3. **添加对手棋盘** — 在战斗盘面上方新增对手 4x7 棋盘（UI 占位）

## 新布局设计

与游戏视角一致：对手在上，我方在下。

```
┌─────────────────────────────────────────────────────┐
│ 棋局态势                                    双栏     │
├─────────────────────────────────────────────────────┤
│ ┌──────┬──────────────────────────────────────────┐ │
│ │      │  对手棋盘 4 x 7  ← 新增，红色主题          │ │
│ │ 装备  │  [响应式 grid，宽度与商店一致]             │ │
│ │      ├──────────────────────────────────────────┤ │
│ │ 弓    │  战斗盘面 4 x 7                           │ │
│ │ 甲    │  [响应式 grid，宽度与商店一致，梅花偏移]   │ │
│ │ 盾    │                                          │ │
│ │ ...  ├──────────────────────────────────────────┤ │
│ │      │  备战席 1 x 9                              │ │
│ │      │  [响应式 grid，宽度与商店一致]             │ │
│ │      ├──────────────────────────────────────────┤ │
│ │      │  实时商店 5 卡                             │ │
│ │      │  [已撑满宽度]                              │ │
│ └──────┴──────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 代码变更

### 唯一修改文件: `ui/pages/status_page.py`

#### 1. 新增实例变量

```python
self._equip_labels = []                                    # 装备标签
self._opponent_cells = [[None] * 7 for _ in range(4)]      # 对手棋盘格子
```

#### 2. 重构 `_build_tactics_pane()` — body 区域改为 grid 两栏

```python
body.grid_columnconfigure(0, weight=0)  # 装备栏，固定宽度
body.grid_columnconfigure(1, weight=1)  # 主内容，撑满

self._build_equipment(body)       # col=0, rowspan=4
self._build_opponent_board(body)  # col=1, row=0  ← 对手在上
self._build_board(body)           # col=1, row=1
self._build_bench(body)           # col=1, row=2
self._build_shop(body)            # col=1, row=3
```

#### 3. 新增 `_build_equipment(parent)`

左侧纵向装备栏，9 个空槽位占位：

```python
equip_frame = ctk.CTkFrame(parent, fg_color=self.PANEL_ALT, corner_radius=7, width=76)
equip_frame.grid(row=0, column=0, rowspan=4, sticky="ns", padx=(0, 6), pady=4)
equip_frame.grid_propagate(False)
# 标题 "装备" + 9 个空 label 槽位
```

#### 4. 新增 `_build_opponent_board(parent)` — 对手棋盘（row=0, col=1）

紧凑 4x7，深紫/暗红配色区分：

```python
opp_frame.grid(row=0, column=1, sticky="ew", padx=4, pady=(4, 8))
# 标题红色 "对手棋盘 4 x 7"
# 4行 x 7列 grid，cell height=36，fg_color="#1a1a2e"
```

#### 5. 修改 `_build_board(parent)` — 响应式（row=1, col=1）

`pack(anchor="w")` → `grid` + `uniform="board"` + `sticky="ew"`

```python
board_frame.grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 8))
for r in range(4):
    row_frame.grid(row=r+1, column=0, sticky="ew",
                   padx=(24 if r % 2 else 4, 4), pady=2)
    for c in range(7):
        row_frame.grid_columnconfigure(c, weight=1, uniform="board")
        cell.grid(row=0, column=c, padx=2, sticky="ew")
```

#### 6. 修改 `_build_bench(parent)` — 响应式（row=2, col=1）

同理改为 `grid` + `uniform="bench"` + `sticky="ew"`

#### 7. 修改 `_build_shop(parent)` — row=3, col=1

仅调整 grid position，布局不变。

#### 8. 修改 `_on_game_state()` — 新增装备和对手棋盘处理

```python
# 装备（UI 占位，数据为空时显示空槽）
equipment = state.get("equipment", [])
for i, lbl in enumerate(self._equip_labels):
    if i < len(equipment) and equipment[i]:
        lbl.configure(text=equipment[i], fg_color="#4a3000", text_color=self.AMBER)
    else:
        lbl.configure(text="", fg_color="transparent")

# 对手棋盘（UI 占位，数据为空时显示空格子）
opponent_board = state.get("opponent_board", [])
# ... 类似 board_state 的渲染逻辑，用深紫/暗红配色
```

## 数据依赖

| 数据字段 | 来源 | 状态 |
|---------|------|------|
| `equipment` | recognizer | 未实现，UI 显示空槽 |
| `opponent_board` | recognizer | 未实现，UI 显示空格子 |

## 修改文件清单

| 文件 | 变更 |
|------|------|
| `ui/pages/status_page.py` | 重构棋局态势面板：响应式布局 + 装备栏 + 对手棋盘 |

仅需修改 **1 个文件**。

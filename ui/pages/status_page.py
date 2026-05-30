"""实时状态页：首页监控、棋盘状态、商店与半自动确认操作。"""

from typing import Any

import cv2
import customtkinter as ctk
from PIL import Image

from core.event_bus import EventBus


class StatusPage(ctk.CTkFrame):
    """首页采用"战术指挥台"布局：状态优先，监控画面可隐藏释放空间。"""

    BG = "#080b10"
    PANEL = "#111827"
    PANEL_ALT = "#0f172a"
    CELL = "#1e293b"
    MUTED = "#94a3b8"
    TEXT = "#e5e7eb"
    GREEN = "#10b981"
    BLUE = "#38bdf8"
    AMBER = "#eab308"
    RED = "#ef4444"

    # 对手棋盘专用配色
    OPP_CELL = "#1a1a2e"
    OPP_OCCUPIED = "#7c2d12"

    def __init__(self, parent, event_bus: EventBus):
        super().__init__(parent, fg_color=self.BG)
        self.event_bus = event_bus
        self._bench_cells = []
        self._board_cells = [[None] * 7 for _ in range(4)]
        self._opponent_cells = [[None] * 7 for _ in range(4)]
        self._shop_labels = []
        self._equip_labels = []
        self._monitor_visible = True
        self._layout_mode = ""
        self._last_img = None
        self._preview_image = None
        self._last_lbl_w = 0
        self._last_lbl_h = 0
        self._build()
        self._bind_events()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_status_bar()
        self._build_main_area()
        self._build_action_bar()

    def _build_status_bar(self):
        self._status_bar = ctk.CTkFrame(self, fg_color=self.PANEL, corner_radius=8)
        self._status_bar.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 10))
        self._status_bar.grid_columnconfigure(5, weight=1)

        title_block = ctk.CTkFrame(self._status_bar, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w", padx=(14, 18), pady=10)
        ctk.CTkLabel(
            title_block,
            text="实时指挥台",
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color=self.TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_block,
            text="ADB / 识别 / 决策",
            font=("Consolas", 10),
            text_color=self.MUTED,
        ).pack(anchor="w", pady=(1, 0))

        self._conn_label = self._status_chip(self._status_bar, "● 未连接", self.RED, 1)
        self._gold_label = self._status_chip(self._status_bar, "金币: --", self.AMBER, 2)
        self._level_label = self._status_chip(self._status_bar, "等级: --", self.BLUE, 3)
        self._stage_label = self._status_chip(self._status_bar, "阶段: --", self.MUTED, 4)

        self._monitor_switch = ctk.CTkSwitch(
            self._status_bar,
            text="显示实时监控",
            font=("Microsoft YaHei UI", 12, "bold"),
            progress_color=self.GREEN,
            button_color=self.TEXT,
            command=self._toggle_monitor,
        )
        self._monitor_switch.grid(row=0, column=6, sticky="e", padx=(12, 14), pady=10)
        self._monitor_switch.select()

    def _status_chip(self, parent, text: str, color: str, column: int) -> ctk.CTkLabel:
        chip = ctk.CTkLabel(
            parent,
            text=text,
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=color,
            fg_color=self.PANEL_ALT,
            corner_radius=6,
            height=34,
        )
        chip.grid(row=0, column=column, sticky="w", padx=4, pady=10)
        return chip

    def _build_main_area(self):
        self._main_content = ctk.CTkFrame(self, fg_color="transparent")
        self._main_content.grid(row=1, column=0, sticky="nsew")
        self._main_content.grid_columnconfigure(0, weight=1)
        self._main_content.grid_columnconfigure(1, weight=1)
        self._main_content.grid_rowconfigure(0, weight=1)

        self._build_monitor_pane()
        self._build_tactics_pane()
        self._main_content.bind("<Configure>", self._on_main_resize)
        self.after(50, self._apply_responsive_layout)

    def _build_monitor_pane(self):
        self._monitor_pane = ctk.CTkFrame(self._main_content, fg_color=self.PANEL, corner_radius=8)
        self._monitor_pane.grid_columnconfigure(0, weight=1)
        self._monitor_pane.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self._monitor_pane, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="实时监控画面",
            font=("Microsoft YaHei UI", 15, "bold"),
            text_color=self.GREEN,
        ).grid(row=0, column=0, sticky="w")
        self._monitor_hint = ctk.CTkLabel(
            header,
            text="自适应缩放",
            font=("Consolas", 10),
            text_color=self.MUTED,
        )
        self._monitor_hint.grid(row=0, column=1, sticky="e")

        self._preview_label = ctk.CTkLabel(
            self._monitor_pane,
            text="等待连接并捕获屏幕中...",
            font=("Microsoft YaHei UI", 14),
            text_color=self.MUTED,
            fg_color="#05070b",
            corner_radius=6,
        )
        self._preview_label.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._preview_label.bind("<Configure>", self._on_label_resize)

    def _build_tactics_pane(self):
        self._tactics_pane = ctk.CTkFrame(self._main_content, fg_color=self.PANEL, corner_radius=8)
        self._tactics_pane.grid_columnconfigure(0, weight=1)
        self._tactics_pane.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self._tactics_pane, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="棋局态势",
            font=("Microsoft YaHei UI", 15, "bold"),
            text_color=self.BLUE,
        ).grid(row=0, column=0, sticky="w")
        self._layout_label = ctk.CTkLabel(header, text="双栏", font=("Consolas", 10), text_color=self.MUTED)
        self._layout_label.grid(row=0, column=1, sticky="e")

        body = ctk.CTkScrollableFrame(self._tactics_pane, fg_color="transparent", corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        # 两栏布局：左侧装备栏(固定窄宽度) + 右侧主内容(撑满)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        self._build_equipment(body)        # col=0, rowspan=4
        self._build_opponent_board(body)   # col=1, row=0  ← 对手在上
        self._build_board(body)            # col=1, row=1
        self._build_bench(body)            # col=1, row=2
        self._build_shop(body)             # col=1, row=3

    def _build_equipment(self, parent):
        """左侧纵向装备栏，9 个槽位（UI 占位）"""
        equip_frame = ctk.CTkFrame(
            parent, fg_color=self.PANEL_ALT, corner_radius=7, width=76,
        )
        equip_frame.grid(row=0, column=0, rowspan=4, sticky="ns", padx=(0, 6), pady=4)
        equip_frame.grid_propagate(False)

        ctk.CTkLabel(
            equip_frame,
            text="装备",
            font=("Microsoft YaHei UI", 11, "bold"),
            text_color=self.AMBER,
        ).pack(pady=(10, 6), padx=4)

        self._equip_labels = []
        for _ in range(9):
            lbl = ctk.CTkLabel(
                equip_frame,
                text="",
                width=64,
                height=26,
                corner_radius=5,
                fg_color="transparent",
                text_color=self.TEXT,
                font=("Microsoft YaHei UI", 10),
            )
            lbl.pack(padx=4, pady=2)
            self._equip_labels.append(lbl)

    def _build_opponent_board(self, parent):
        """对手棋盘 4x7，紧凑布局，深紫配色区分"""
        opp_frame = ctk.CTkFrame(parent, fg_color="transparent")
        opp_frame.grid(row=0, column=1, sticky="ew", padx=4, pady=(4, 8))
        opp_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            opp_frame,
            text="对手棋盘 4 x 7",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=self.RED,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 6))

        for r in range(4):
            row_frame = ctk.CTkFrame(opp_frame, fg_color="transparent")
            row_frame.grid(row=r + 1, column=0, sticky="ew",
                           padx=(24 if r % 2 else 6, 6), pady=2)
            for c in range(7):
                row_frame.grid_columnconfigure(c, weight=1, uniform="opp")
                cell = ctk.CTkLabel(
                    row_frame,
                    text="+",
                    font=("Microsoft YaHei UI", 9, "bold"),
                    height=36,
                    corner_radius=7,
                    fg_color=self.OPP_CELL,
                    text_color="#64748b",
                )
                cell.grid(row=0, column=c, padx=2, sticky="ew")
                self._opponent_cells[r][c] = cell

    def _build_board(self, parent):
        """我方战斗盘面 4x7，响应式 grid 布局"""
        board_frame = ctk.CTkFrame(parent, fg_color="transparent")
        board_frame.grid(row=1, column=1, sticky="ew", padx=4, pady=(0, 8))
        board_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            board_frame,
            text="战斗盘面 4 x 7",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=self.MUTED,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 6))

        for r in range(4):
            row_frame = ctk.CTkFrame(board_frame, fg_color="transparent")
            row_frame.grid(row=r + 1, column=0, sticky="ew",
                           padx=(24 if r % 2 else 6, 6), pady=2)
            for c in range(7):
                row_frame.grid_columnconfigure(c, weight=1, uniform="board")
                cell = ctk.CTkLabel(
                    row_frame,
                    text="+",
                    font=("Microsoft YaHei UI", 10, "bold"),
                    height=44,
                    corner_radius=8,
                    fg_color=self.CELL,
                    text_color="#64748b",
                )
                cell.grid(row=0, column=c, padx=2, sticky="ew")
                self._board_cells[r][c] = cell

    def _build_bench(self, parent):
        """备战席 1x9，响应式 grid 布局"""
        bench_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bench_frame.grid(row=2, column=1, sticky="ew", padx=4, pady=(0, 8))
        bench_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bench_frame,
            text="备战席 1 x 9",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=self.MUTED,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 6))

        row_bench = ctk.CTkFrame(bench_frame, fg_color="transparent")
        row_bench.grid(row=1, column=0, sticky="ew")
        for i in range(9):
            row_bench.grid_columnconfigure(i, weight=1, uniform="bench")
            cell = ctk.CTkLabel(
                row_bench,
                text="-",
                font=("Microsoft YaHei UI", 10, "bold"),
                height=36,
                corner_radius=7,
                fg_color=self.CELL,
                text_color="#64748b",
            )
            cell.grid(row=0, column=i, padx=2, sticky="ew")
            self._bench_cells.append(cell)

    def _build_shop(self, parent):
        """实时商店 5 卡，响应式布局"""
        shop_panel = ctk.CTkFrame(parent, fg_color="transparent")
        shop_panel.grid(row=3, column=1, sticky="ew", padx=4, pady=(0, 8))
        shop_panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            shop_panel,
            text="实时商店",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=self.MUTED,
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(0, 6))

        row_shop = ctk.CTkFrame(shop_panel, fg_color="transparent")
        row_shop.grid(row=1, column=0, sticky="ew", padx=6)
        for i in range(5):
            row_shop.grid_columnconfigure(i, weight=1, uniform="shop")
            card = ctk.CTkLabel(
                row_shop,
                text="--",
                font=("Microsoft YaHei UI", 11, "bold"),
                height=42,
                corner_radius=7,
                fg_color=self.CELL,
                text_color="#64748b",
            )
            card.grid(row=0, column=i, sticky="ew", padx=2)
            self._shop_labels.append(card)

    def _build_action_bar(self):
        action_bar = ctk.CTkFrame(self, fg_color=self.PANEL, height=72, corner_radius=8)
        action_bar.grid(row=2, column=0, sticky="ew", padx=2, pady=(10, 0))
        action_bar.grid_columnconfigure(2, weight=1)
        action_bar.grid_propagate(False)

        self._confirm_btn = ctk.CTkButton(
            action_bar,
            text="确认决策操作",
            width=136,
            height=38,
            state="disabled",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg_color=self.GREEN,
            hover_color="#059669",
            corner_radius=7,
            command=self._on_confirm,
        )
        self._confirm_btn.grid(row=0, column=0, sticky="w", padx=(14, 8), pady=16)

        self._reject_btn = ctk.CTkButton(
            action_bar,
            text="跳过动作",
            width=96,
            height=38,
            state="disabled",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg_color=self.RED,
            hover_color="#dc2626",
            corner_radius=7,
            command=self._on_reject,
        )
        self._reject_btn.grid(row=0, column=1, sticky="w", padx=4, pady=16)

        self._pending_label = ctk.CTkLabel(
            action_bar,
            text="暂无待确认动作",
            font=("Microsoft YaHei UI", 12, "bold"),
            text_color=self.MUTED,
            anchor="w",
        )
        self._pending_label.grid(row=0, column=2, sticky="ew", padx=(12, 14), pady=16)

    def _bind_events(self):
        self.event_bus.on("device_connected", self._on_connected)
        self.event_bus.on("device_disconnected", self._on_disconnected)
        self.event_bus.on("game_state_updated", self._on_game_state)
        self.event_bus.on("screenshot_ready", self._on_screenshot)
        self.event_bus.on("action_pending_confirm", self._on_pending)

    def _on_main_resize(self, _event=None):
        self._apply_responsive_layout()

    def _apply_responsive_layout(self):
        if not hasattr(self, "_main_content"):
            return

        width = self._main_content.winfo_width()
        mode = "hidden" if not self._monitor_visible else ("stacked" if width < 980 else "split")
        if mode == self._layout_mode:
            return
        self._layout_mode = mode

        self._monitor_pane.grid_forget()
        self._tactics_pane.grid_forget()
        self._main_content.grid_columnconfigure(0, weight=1)
        self._main_content.grid_columnconfigure(1, weight=1)

        if mode == "hidden":
            self._main_content.grid_rowconfigure(0, weight=1)
            self._main_content.grid_rowconfigure(1, weight=0)
            self._tactics_pane.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=0)
            self._layout_label.configure(text="监控隐藏")
        elif mode == "stacked":
            self._main_content.grid_rowconfigure(0, weight=1)
            self._main_content.grid_rowconfigure(1, weight=1)
            self._monitor_pane.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=(0, 8))
            self._tactics_pane.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=0, pady=(8, 0))
            self._layout_label.configure(text="窄屏堆叠")
        else:
            self._main_content.grid_rowconfigure(0, weight=1)
            self._main_content.grid_rowconfigure(1, weight=0)
            self._monitor_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=0)
            self._tactics_pane.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=0)
            self._layout_label.configure(text="双栏")

        self.after(50, self._update_preview)

    def _toggle_monitor(self):
        self._monitor_visible = bool(self._monitor_switch.get())
        self._apply_responsive_layout()
        if self._monitor_visible:
            self._update_preview()

    def _on_connected(self, data: dict | None = None):
        model = data.get("model") if isinstance(data, dict) else None
        label = f"● 已连接 {model}" if model else "● 已连接设备"
        self._conn_label.configure(text=label, text_color=self.GREEN)

    def _on_disconnected(self, _data=None):
        self._conn_label.configure(text="● 未连接设备", text_color=self.RED)
        self._gold_label.configure(text="金币: --")
        self._level_label.configure(text="等级: --")
        self._stage_label.configure(text="阶段: --")

    def _on_game_state(self, state: dict[str, Any]):
        gold = state.get("gold", "--")
        level = state.get("level", "--")
        stage = state.get("stage", "--")
        self._gold_label.configure(text=f"金币: {gold}")
        self._level_label.configure(text=f"等级: {level}")
        self._stage_label.configure(text=f"阶段: {stage}")

        # 商店弈子
        shop_champions = state.get("shop_champions", [])
        if shop_champions and len(shop_champions) == 5:
            for i, name in enumerate(shop_champions):
                label = self._shop_labels[i]
                if name:
                    label.configure(text=name, fg_color="#1e1b4b", text_color=self.BLUE)
                else:
                    label.configure(text="空卡槽", fg_color=self.CELL, text_color="#64748b")

        # 我方棋盘
        board_state = state.get("board_state", [])
        if board_state:
            for r in range(min(4, len(board_state))):
                for c in range(min(7, len(board_state[r]))):
                    item = board_state[r][c]
                    cell = self._board_cells[r][c]
                    if item:
                        name = item.get("name", "在场弈子")
                        star = item.get("star", 1)
                        fg = "#b58900" if name == "在场弈子" else "#047857"
                        cell.configure(fg_color=fg, text_color="white", text=f"{name}\n{star}★")
                    else:
                        cell.configure(fg_color=self.CELL, text_color="#64748b", text="+")

        # 备战席
        bench_state = state.get("bench_state", [])
        if bench_state:
            for i in range(min(9, len(bench_state))):
                item = bench_state[i]
                cell = self._bench_cells[i]
                if item:
                    name = item.get("name", "弈子")
                    star = item.get("star", 1)
                    cell.configure(fg_color="#1d4ed8", text_color="white", text=f"{name}\n{star}★")
                else:
                    cell.configure(fg_color=self.CELL, text_color="#64748b", text="-")

        # 装备栏（UI 占位，数据为空时显示空槽）
        equipment = state.get("equipment", [])
        for i, lbl in enumerate(self._equip_labels):
            if i < len(equipment) and equipment[i]:
                lbl.configure(text=equipment[i], fg_color="#4a3000", text_color=self.AMBER)
            else:
                lbl.configure(text="", fg_color="transparent")

        # 对手棋盘（UI 占位，数据为空时显示空格子）
        opponent_board = state.get("opponent_board", [])
        if opponent_board:
            for r in range(min(4, len(opponent_board))):
                for c in range(min(7, len(opponent_board[r]))):
                    item = opponent_board[r][c]
                    cell = self._opponent_cells[r][c]
                    if item:
                        name = item.get("name", "?")
                        star = item.get("star", 1)
                        cell.configure(
                            fg_color=self.OPP_OCCUPIED, text_color="white",
                            text=f"{name}\n{star}★",
                        )
                    else:
                        cell.configure(fg_color=self.OPP_CELL, text_color="#64748b", text="+")

    def _on_screenshot(self, img):
        self._last_img = img
        if self._monitor_visible:
            self._update_preview()

    def _on_label_resize(self, event):
        if self._last_img is None or not self._monitor_visible:
            return

        new_w = event.width
        new_h = event.height
        if abs(new_w - self._last_lbl_w) > 10 or abs(new_h - self._last_lbl_h) > 10:
            self._last_lbl_w = new_w
            self._last_lbl_h = new_h
            self._update_preview()

    def _update_preview(self):
        if self._last_img is None or not self._monitor_visible:
            return

        lbl_w = self._last_lbl_w or self._preview_label.winfo_width()
        lbl_h = self._last_lbl_h or self._preview_label.winfo_height()
        if lbl_w <= 10 or lbl_h <= 10:
            return

        max_w = max(lbl_w - 18, 120)
        max_h = max(lbl_h - 18, 120)
        h, w = self._last_img.shape[:2]
        scale = min(max_w / w, max_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w <= 0 or new_h <= 0:
            return

        resized = cv2.resize(self._last_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        self._preview_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
        self._preview_label.configure(image=self._preview_image, text="")

    def _on_pending(self, action: dict):
        reason = action.get("reason", "未知操作")
        self._pending_label.configure(text=f"待确认: {reason}", text_color=self.AMBER)
        self._confirm_btn.configure(state="normal")
        self._reject_btn.configure(state="normal")

    def _on_confirm(self):
        self._pending_label.configure(text="暂无待确认动作", text_color=self.MUTED)
        self._confirm_btn.configure(state="disabled")
        self._reject_btn.configure(state="disabled")
        self.event_bus.emit("user_confirm_action")

    def _on_reject(self):
        self._pending_label.configure(text="暂无待确认动作", text_color=self.MUTED)
        self._confirm_btn.configure(state="disabled")
        self._reject_btn.configure(state="disabled")
        self.event_bus.emit("user_reject_action")

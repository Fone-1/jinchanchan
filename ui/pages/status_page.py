"""实时状态页 — 显示连接状态、游戏状态、截图预览"""

import customtkinter as ctk
from PIL import Image
import cv2

from core.event_bus import EventBus


class StatusPage(ctk.CTkFrame):
    def __init__(self, parent, event_bus: EventBus):
        super().__init__(parent)
        self.event_bus = event_bus
        self._build()
        self._bind_events()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 顶部状态栏
        status_bar = ctk.CTkFrame(self, height=50)
        status_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_bar.grid_propagate(False)

        self._conn_label = ctk.CTkLabel(status_bar, text="● 未连接", text_color="red", font=("", 14))
        self._conn_label.pack(side="left", padx=15, pady=10)

        self._gold_label = ctk.CTkLabel(status_bar, text="金币: --")
        self._gold_label.pack(side="left", padx=15)

        self._level_label = ctk.CTkLabel(status_bar, text="等级: --")
        self._level_label.pack(side="left", padx=15)

        self._stage_label = ctk.CTkLabel(status_bar, text="阶段: --")
        self._stage_label.pack(side="left", padx=15)

        # 截图预览区
        self._preview_label = ctk.CTkLabel(self, text="等待截图...", font=("", 16))
        self._preview_label.grid(row=1, column=0, sticky="nsew")

        # 底部操作栏
        action_bar = ctk.CTkFrame(self, height=80)
        action_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        action_bar.grid_propagate(False)

        self._confirm_btn = ctk.CTkButton(
            action_bar, text="确认操作", width=120, state="disabled",
            command=self._on_confirm,
        )
        self._confirm_btn.pack(side="left", padx=15, pady=15)

        self._reject_btn = ctk.CTkButton(
            action_bar, text="跳过", width=80, state="disabled",
            command=self._on_reject,
        )
        self._reject_btn.pack(side="left", padx=5, pady=15)

        self._pending_label = ctk.CTkLabel(action_bar, text="")
        self._pending_label.pack(side="left", padx=15)

    def _bind_events(self):
        self.event_bus.on("device_connected", self._on_connected)
        self.event_bus.on("device_disconnected", self._on_disconnected)
        self.event_bus.on("game_state_updated", self._on_game_state)
        self.event_bus.on("screenshot_ready", self._on_screenshot)
        self.event_bus.on("action_pending_confirm", self._on_pending)

    def _on_connected(self, _data=None):
        self._conn_label.configure(text="● 已连接", text_color="green")

    def _on_disconnected(self, _data=None):
        self._conn_label.configure(text="● 未连接", text_color="red")

    def _on_game_state(self, state: dict):
        gold = state.get("gold", "--")
        level = state.get("level", "--")
        self._gold_label.configure(text=f"金币: {gold}")
        self._level_label.configure(text=f"等级: {level}")

    def _on_screenshot(self, img):
        """显示最新截图"""
        h, w = img.shape[:2]
        # 缩放到预览尺寸
        max_w, max_h = 720, 400
        scale = min(max_w / w, max_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(img, (new_w, new_h))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(new_w, new_h))
        self._preview_label.configure(image=ctk_img, text="")

    def _on_pending(self, action: dict):
        """半自动模式：待确认操作"""
        reason = action.get("reason", "未知操作")
        self._pending_label.configure(text=f"待确认: {reason}")
        self._confirm_btn.configure(state="normal")
        self._reject_btn.configure(state="normal")

    def _on_confirm(self):
        self._pending_label.configure(text="")
        self._confirm_btn.configure(state="disabled")
        self._reject_btn.configure(state="disabled")
        self.event_bus.emit("user_confirm_action")

    def _on_reject(self):
        self._pending_label.configure(text="")
        self._confirm_btn.configure(state="disabled")
        self._reject_btn.configure(state="disabled")
        self.event_bus.emit("user_reject_action")

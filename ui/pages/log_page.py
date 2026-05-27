"""操作日志页 — 实时显示所有操作记录"""

import customtkinter as ctk
from datetime import datetime

from core.event_bus import EventBus


class LogPage(ctk.CTkFrame):
    def __init__(self, parent, event_bus: EventBus):
        super().__init__(parent)
        self.event_bus = event_bus
        self._build()
        self._bind_events()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkLabel(self, text="操作日志", font=("", 16, "bold"))
        header.grid(row=0, column=0, sticky="w", pady=(0, 10))

        self._textbox = ctk.CTkTextbox(self, state="disabled", font=("Consolas", 12))
        self._textbox.grid(row=1, column=0, sticky="nsew")

        clear_btn = ctk.CTkButton(self, text="清空日志", width=100, command=self._clear)
        clear_btn.grid(row=2, column=0, sticky="e", pady=(10, 0))

    def _bind_events(self):
        self.event_bus.on("action_executed", self._on_action_executed)
        self.event_bus.on("action_pending_confirm", self._on_action_pending)
        self.event_bus.on("game_state_updated", self._on_game_state)
        self.event_bus.on("device_connected", lambda _: self._log("系统", "设备已连接"))
        self.event_bus.on("device_disconnected", lambda _: self._log("系统", "设备已断开"))

    def _log(self, category: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] [{category}] {message}\n"
        self._textbox.configure(state="normal")
        self._textbox.insert("end", line)
        self._textbox.see("end")
        self._textbox.configure(state="disabled")

    def _on_action_executed(self, result: dict):
        action = result.get("action", {})
        success = result.get("success", False)
        action_type = action.get("type", "unknown")
        champion = action.get("champion", "")
        status = "成功" if success else "失败"
        self._log("执行", f"{action_type} {champion} - {status}")

    def _on_action_pending(self, action: dict):
        reason = action.get("reason", "")
        self._log("待确认", reason)

    def _on_game_state(self, _state: dict):
        # MVP 阶段不在日志中输出每次状态更新，避免刷屏
        pass

    def _clear(self):
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

"""主窗口 — CustomTkinter 应用框架"""

import customtkinter as ctk

from core.event_bus import EventBus
from core.config_manager import ConfigManager
from ui.pages.status_page import StatusPage
from ui.pages.log_page import LogPage
from ui.pages.settings_page import SettingsPage
from ui.pages.data_page import DataPage


class App(ctk.CTk):
    def __init__(self, event_bus: EventBus, config: dict, config_mgr: ConfigManager, debug_manager=None):
        super().__init__()
        self.event_bus = event_bus
        self.config = config
        self.config_mgr = config_mgr
        self._debug_manager = debug_manager

        self.title(config.get("app", {}).get("name", "金铲铲智能助手"))
        self.geometry("960x640")
        self.minsize(800, 500)

        ctk.set_appearance_mode(config.get("ui", {}).get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        self._build_layout()
        self._bind_events()

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 左侧导航栏
        self._sidebar = ctk.CTkFrame(self, width=160, corner_radius=0)
        self._sidebar.grid(row=0, column=0, sticky="nsw")
        self._sidebar.grid_propagate(False)

        self._build_sidebar()

        # 右侧内容区
        self._content_frame = ctk.CTkFrame(self, corner_radius=0)
        self._content_frame.grid(row=0, column=1, sticky="nsew")
        self._content_frame.grid_columnconfigure(0, weight=1)
        self._content_frame.grid_rowconfigure(0, weight=1)

        # 创建页面
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._pages["status"] = StatusPage(self._content_frame, self.event_bus)
        self._pages["log"] = LogPage(self._content_frame, self.event_bus)
        self._pages["data"] = DataPage(self._content_frame, self.event_bus, self.config_mgr)
        self._pages["settings"] = SettingsPage(self._content_frame, self.event_bus, self.config_mgr)

        if self._debug_manager:
            from ui.pages.debug_page import DebugPage
            self._pages["debug"] = DebugPage(self._content_frame, self._debug_manager)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self._show_page("status")

    def _build_sidebar(self):
        title = ctk.CTkLabel(self._sidebar, text="金铲铲助手", font=("", 18, "bold"))
        title.pack(pady=(20, 10), padx=10)

        # 总开关 — 默认关闭
        self._task_running = False
        self._task_btn = ctk.CTkButton(
            self._sidebar,
            text="▶ 启动任务",
            height=44,
            font=("", 16, "bold"),
            fg_color="green",
            hover_color="darkgreen",
            command=self._toggle_task,
        )
        self._task_btn.pack(fill="x", padx=10, pady=(0, 20))

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("status", "实时状态"),
            ("log", "操作日志"),
            ("data", "数据管理"),
        ]
        if self._debug_manager:
            nav_items.append(("debug", "调试面板"))
        for key, label in nav_items:
            btn = ctk.CTkButton(
                self._sidebar,
                text=label,
                anchor="w",
                height=36,
                command=lambda k=key: self._show_page(k),
            )
            btn.pack(fill="x", padx=10, pady=4)
            self._nav_buttons[key] = btn

        # 底部区域
        self._sidebar.pack_propagate(False)
        bottom_frame = ctk.CTkFrame(self._sidebar, fg_color="transparent")
        bottom_frame.pack(side="bottom", fill="x", padx=10, pady=10)

        # 设置按钮（底部）
        settings_btn = ctk.CTkButton(
            bottom_frame,
            text="设置",
            anchor="w",
            height=36,
            command=lambda: self._show_page("settings"),
        )
        settings_btn.pack(fill="x", pady=(0, 8))
        self._nav_buttons["settings"] = settings_btn

        # 模式切换
        ctk.CTkLabel(bottom_frame, text="自动化模式:").pack(anchor="w")
        self._mode_switch = ctk.CTkSwitch(
            bottom_frame,
            text="全自动",
            command=self._toggle_mode,
        )
        self._mode_switch.pack(anchor="w", pady=5)

    def _show_page(self, name: str):
        page = self._pages.get(name)
        if page:
            page.tkraise()
            for key, btn in self._nav_buttons.items():
                btn.configure(fg_color=("gray75", "gray25") if key == name else ("gray85", "gray15"))

    def _toggle_task(self):
        self._task_running = not self._task_running
        if self._task_running:
            self._task_btn.configure(text="■ 停止任务", fg_color="red", hover_color="darkred")
        else:
            self._task_btn.configure(text="▶ 启动任务", fg_color="green", hover_color="darkgreen")
        self.event_bus.emit("task_toggled", self._task_running)

    def _toggle_mode(self):
        mode = "full_auto" if self._mode_switch.get() else "semi_auto"
        self.event_bus.emit("mode_changed", mode)

    def _bind_events(self):
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self.event_bus.emit("app_closing")
        self.destroy()

    @property
    def settings_page(self) -> SettingsPage:
        return self._pages.get("settings")

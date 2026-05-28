"""调试面板 — 事件流监控、插件状态检查、事件模拟"""

import json
import logging
from datetime import datetime
from tkinter import filedialog

import cv2
import customtkinter as ctk

from core.debug_manager import DebugManager

logger = logging.getLogger(__name__)


class DebugPage(ctk.CTkFrame):
    def __init__(self, parent, debug_manager: DebugManager):
        super().__init__(parent)
        self._dm = debug_manager
        self._selected_plugin = None
        self._selected_event_index = None
        self._paused = False
        self._plugin_frames: list = []
        self._build()
        self._build_plugin_list()
        self._start_polling()

    # ── 构建 UI ──

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 顶部工具栏
        toolbar = ctk.CTkFrame(self, height=40)
        toolbar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))

        ctk.CTkLabel(toolbar, text="调试面板", font=("", 16, "bold")).pack(side="left", padx=10)

        self._monitor_switch = ctk.CTkSwitch(
            toolbar, text="事件监控", command=self._toggle_monitoring
        )
        self._monitor_switch.pack(side="left", padx=15)
        if self._dm.is_monitoring:
            self._monitor_switch.select()

        ctk.CTkButton(toolbar, text="清空日志", width=80, command=self._clear_log).pack(side="left", padx=5)

        self._pause_btn = ctk.CTkButton(toolbar, text="暂停滚动", width=80, command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=5)

        # 左侧：插件列表
        left = ctk.CTkFrame(self, width=160)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        left.grid_propagate(False)

        ctk.CTkLabel(left, text="插件列表", font=("", 13, "bold")).pack(pady=(8, 4), padx=8, anchor="w")

        self._plugin_list_frame = ctk.CTkScrollableFrame(left)
        self._plugin_list_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self._plugin_buttons: dict[str, ctk.CTkButton] = {}

        # 中间：选项卡
        mid = ctk.CTkFrame(self)
        mid.grid(row=1, column=1, sticky="nsew", padx=(0, 6))
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_rowconfigure(1, weight=1)

        # 选项卡按钮
        tab_bar = ctk.CTkFrame(mid, height=36)
        tab_bar.grid(row=0, column=0, sticky="ew")

        self._tab = "events"
        self._events_tab_btn = ctk.CTkButton(
            tab_bar, text="事件流", width=80, height=28,
            command=lambda: self._switch_tab("events")
        )
        self._events_tab_btn.pack(side="left", padx=4, pady=4)

        self._status_tab_btn = ctk.CTkButton(
            tab_bar, text="插件状态", width=80, height=28,
            command=lambda: self._switch_tab("status")
        )
        self._status_tab_btn.pack(side="left", padx=4, pady=4)

        # 事件过滤
        self._filter_entry = ctk.CTkEntry(tab_bar, placeholder_text="过滤事件名...", width=160)
        self._filter_entry.pack(side="right", padx=8, pady=4)

        # 事件流视图
        self._events_frame = ctk.CTkFrame(mid)
        self._events_frame.grid(row=1, column=0, sticky="nsew")
        self._events_frame.grid_columnconfigure(0, weight=1)
        self._events_frame.grid_rowconfigure(0, weight=1)

        self._events_textbox = ctk.CTkTextbox(self._events_frame, state="disabled", font=("Consolas", 11))
        self._events_textbox.grid(row=0, column=0, sticky="nsew")
        self._events_textbox.bind("<ButtonRelease-1>", self._on_event_click)

        # 插件状态视图
        self._status_frame = ctk.CTkFrame(mid)

        self._status_textbox = ctk.CTkTextbox(self._status_frame, state="disabled", font=("Consolas", 11))
        self._status_textbox.pack(fill="both", expand=True)

        # 右侧：详情/模拟
        right = ctk.CTkFrame(self, width=280)
        right.grid(row=1, column=2, sticky="nsew")
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        # 事件详情
        detail_label = ctk.CTkLabel(right, text="事件详情", font=("", 13, "bold"))
        detail_label.grid(row=0, column=0, sticky="sw", padx=8, pady=(8, 2))

        self._detail_textbox = ctk.CTkTextbox(right, state="disabled", font=("Consolas", 11))
        self._detail_textbox.grid(row=1, column=0, sticky="nsew", padx=4)

        right.grid_rowconfigure(1, weight=1)

        # 事件模拟
        sim_frame = ctk.CTkFrame(right)
        sim_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=(6, 4))
        sim_frame.grid_columnconfigure(0, weight=1)
        sim_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(sim_frame, text="事件模拟", font=("", 13, "bold")).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 2)
        )

        self._sim_event_combo = ctk.CTkComboBox(sim_frame, values=[""], width=240)
        self._sim_event_combo.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self._sim_event_combo.set("")

        self._sim_data_entry = ctk.CTkTextbox(sim_frame, font=("Consolas", 11), height=80)
        self._sim_data_entry.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self._sim_data_entry.insert("1.0", "{}")

        btn_row = ctk.CTkFrame(sim_frame, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(btn_row, text="发送事件", command=self._emit_simulated_event).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ctk.CTkButton(btn_row, text="加载图片", command=self._load_and_emit_image).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )

        self._switch_tab("events")

    # ── 选项卡切换 ──

    def _switch_tab(self, tab: str):
        self._tab = tab
        if tab == "events":
            self._events_frame.grid(row=1, column=0, sticky="nsew")
            self._status_frame.grid_forget()
            self._events_tab_btn.configure(fg_color=("gray75", "gray25"))
            self._status_tab_btn.configure(fg_color=("gray85", "gray15"))
            self._update_sim_event_list()
        else:
            self._events_frame.grid_forget()
            self._status_frame.grid(row=1, column=0, sticky="nsew")
            self._events_tab_btn.configure(fg_color=("gray85", "gray15"))
            self._status_tab_btn.configure(fg_color=("gray75", "gray25"))
            self._refresh_plugin_status()

    # ── 插件列表 ──

    def _build_plugin_list(self):
        plugins = self._dm.get_plugin_list()

        # 清理旧的 frame（销毁 frame 会自动销毁其子组件）
        for frame in self._plugin_frames:
            frame.destroy()
        self._plugin_frames.clear()
        self._plugin_buttons.clear()

        for info in plugins:
            name = info["name"]
            running = info["is_running"]
            indicator = "●" if running else "○"
            color = "green" if running else "red"

            btn_frame = ctk.CTkFrame(self._plugin_list_frame, fg_color="transparent")
            btn_frame.pack(fill="x", padx=2, pady=2)
            self._plugin_frames.append(btn_frame)

            dot = ctk.CTkLabel(btn_frame, text=indicator, text_color=color, width=20, font=("", 14))
            dot.pack(side="left")

            btn = ctk.CTkButton(
                btn_frame, text=name, anchor="w", height=28, fg_color="transparent",
                text_color=("gray10", "gray90"),
                command=lambda n=name: self._select_plugin(n),
            )
            btn.pack(side="left", fill="x", expand=True)
            self._plugin_buttons[name] = btn

    def _select_plugin(self, name: str):
        self._selected_plugin = name
        # 高亮选中
        for n, btn in self._plugin_buttons.items():
            btn.configure(fg_color=("gray75", "gray25") if n == name else "transparent")
        self._switch_tab("status")

    # ── 事件流 ──

    def _refresh_event_log(self):
        if self._paused:
            return

        event_filter = self._filter_entry.get().strip() or None
        events = self._dm.get_event_log(event_filter=event_filter, limit=200)

        self._events_textbox.configure(state="normal")

        # 记录当前滚动位置
        current_pos = self._events_textbox.yview()

        self._events_textbox.delete("1.0", "end")
        for evt in events:
            ts = datetime.fromtimestamp(evt["timestamp"]).strftime("%H:%M:%S.%f")[:-3]
            source = evt["source"]
            event_name = evt["event_name"]
            summary = evt["data_summary"]
            handlers = evt["handler_count"]

            line = f"{ts}  [{source}]  {event_name}  ({handlers}h)\n"
            self._events_textbox.insert("end", line)

            if summary:
                self._events_textbox.insert("end", f"    {summary}\n")

        self._events_textbox.configure(state="disabled")

        # 自动滚动到底部
        if not self._paused:
            self._events_textbox.see("end")

    # ── 插件状态 ──

    def _refresh_plugin_status(self):
        if not self._selected_plugin:
            self._status_textbox.configure(state="normal")
            self._status_textbox.delete("1.0", "end")
            self._status_textbox.insert("1.0", "请在左侧选择一个插件")
            self._status_textbox.configure(state="disabled")
            return

        info = self._dm.get_plugin_info(self._selected_plugin)
        if not info:
            return

        lines = []
        lines.append(f"=== {info['name']} ===\n")
        lines.append(f"运行状态: {'运行中' if info['is_running'] else '已停止'}\n\n")

        lines.append("--- 事件订阅 ---\n")
        subs = info.get("subscriptions", [])
        if subs:
            for event in subs:
                lines.append(f"  • {event}\n")
        else:
            lines.append("  (无)\n")

        lines.append("\n--- 配置参数 ---\n")
        config = info.get("config", {})
        if config:
            for key, value in config.items():
                lines.append(f"  {key}: {value}\n")
        else:
            lines.append("  (空)\n")

        lines.append("\n--- 运行时状态 ---\n")
        runtime = info.get("runtime", {})
        if runtime:
            for key, value in runtime.items():
                lines.append(f"  {key}: {value}\n")
        else:
            lines.append("  (插件未实现 get_debug_info)\n")

        self._status_textbox.configure(state="normal")
        self._status_textbox.delete("1.0", "end")
        self._status_textbox.insert("1.0", "".join(lines))
        self._status_textbox.configure(state="disabled")

    # ── 事件详情 ──

    def _on_event_click(self, _event=None):
        """点击事件流中的某行，显示详情"""
        try:
            index = self._events_textbox.index("insert")
            line_num = int(index.split(".")[0])
            # 每条事件占 1-2 行，找到对应的事件索引
            event_filter = self._filter_entry.get().strip() or None
            events = self._dm.get_event_log(event_filter=event_filter, limit=200)

            # 计算点击的是哪条事件
            event_idx = 0
            current_line = 1
            for i, evt in enumerate(events):
                end_line = current_line + (2 if evt["data_summary"] else 1)
                if current_line <= line_num < end_line:
                    event_idx = i
                    break
                current_line = end_line

            if event_idx < len(events):
                evt = events[event_idx]
                self._show_event_detail(evt)
        except Exception:
            pass

    def _show_event_detail(self, evt: dict):
        ts = datetime.fromtimestamp(evt["timestamp"]).strftime("%H:%M:%S.%f")[:-3]
        detail = {
            "timestamp": ts,
            "event_name": evt["event_name"],
            "source": evt["source"],
            "handler_count": evt["handler_count"],
            "data_summary": evt["data_summary"],
        }

        self._detail_textbox.configure(state="normal")
        self._detail_textbox.delete("1.0", "end")
        self._detail_textbox.insert("1.0", json.dumps(detail, indent=2, ensure_ascii=False))
        self._detail_textbox.configure(state="disabled")

    # ── 事件模拟 ──

    def _emit_simulated_event(self):
        event_name = self._sim_event_combo.get().strip()
        if not event_name:
            return

        data_str = self._sim_data_entry.get("1.0", "end").strip()
        data = None
        if data_str:
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                # 非 JSON 格式，作为字符串传入
                data = data_str

        self._dm.event_bus.emit(event_name, data)
        self._update_sim_event_list()

    def _load_and_emit_image(self):
        """加载图片文件，直接调用识别插件处理，不走截图循环和决策链路"""
        path = filedialog.askopenfilename(
            title="选择截图",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")]
        )
        if not path:
            return

        img = cv2.imread(path)
        if img is None:
            logger.error(f"无法读取图片: {path}")
            return

        logger.info(f"加载图片: {path} (尺寸: {img.shape})")

        # 直接调用识别插件的 _analyze，绕过截图循环和决策链路
        recognizer = self._dm.get_plugin("recognizer")
        if recognizer is None:
            logger.error("识别插件未注册")
            return

        result = recognizer._analyze(img)
        if result:
            # 移除 raw_image 避免在日志中打印巨大数组
            display = {k: v for k, v in result.items() if k != "raw_image"}
            logger.info(f"识别结果: {display}")
            # 通过事件总线输出结果，会出现在事件流中
            self._dm.event_bus.emit("game_state_updated", result)
        else:
            logger.warning("识别返回空结果")

    # ── 控制 ──

    def _toggle_monitoring(self):
        enabled = self._monitor_switch.get()
        self._dm.set_monitoring(enabled)

    def _clear_log(self):
        self._dm.clear_event_log()
        self._events_textbox.configure(state="normal")
        self._events_textbox.delete("1.0", "end")
        self._events_textbox.configure(state="disabled")

    def _toggle_pause(self):
        self._paused = not self._paused
        self._pause_btn.configure(text="继续滚动" if self._paused else "暂停滚动")

    # ── 轮询 ──

    def _start_polling(self):
        self._refresh_event_log()
        self.after(200, self._start_polling)

    def _update_sim_event_list(self):
        events = self._dm.get_all_event_names()
        if events:
            current = self._sim_event_combo.get()
            self._sim_event_combo.configure(values=events)
            if current not in events:
                self._sim_event_combo.set(events[0])

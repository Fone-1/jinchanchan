"""设置页 — 模拟器连接配置管理"""

import threading
import customtkinter as ctk
from tkinter import messagebox
from typing import Any

from core.event_bus import EventBus
from core.config_manager import ConfigManager
from plugins.adb_connector.plugin import EMULATOR_PRESETS


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, event_bus: EventBus, config_mgr: ConfigManager):
        super().__init__(parent)
        self.event_bus = event_bus
        self.config_mgr = config_mgr
        self._adb_plugin = None
        self._build()
        self._load_profiles()

    def set_adb_plugin(self, plugin):
        self._adb_plugin = plugin

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # === ADB 连接配置区域 ===
        section = ctk.CTkFrame(self)
        section.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        section.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(section, text="模拟器连接配置", font=("", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=15, pady=(15, 10)
        )

        # 配置方案选择
        ctk.CTkLabel(section, text="配置方案:").grid(row=1, column=0, sticky="e", padx=(15, 5), pady=5)
        self._profile_combo = ctk.CTkComboBox(section, values=[], width=200, command=self._on_profile_switch)
        self._profile_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        btn_frame = ctk.CTkFrame(section, fg_color="transparent")
        btn_frame.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        ctk.CTkButton(btn_frame, text="新建", width=60, command=self._new_profile).pack(side="left", padx=2)
        ctk.CTkButton(btn_frame, text="删除", width=60, fg_color="gray50", command=self._delete_profile).pack(side="left", padx=2)

        # 表单字段
        row = 2
        ctk.CTkLabel(section, text="名称:").grid(row=row, column=0, sticky="e", padx=(15, 5), pady=5)
        self._name_entry = ctk.CTkEntry(section, width=250)
        self._name_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)

        row += 1
        ctk.CTkLabel(section, text="模拟器:").grid(row=row, column=0, sticky="e", padx=(15, 5), pady=5)
        preset_labels = [v["label"] for v in EMULATOR_PRESETS.values()]
        self._emulator_combo = ctk.CTkComboBox(section, values=preset_labels, width=250, command=self._on_emulator_change)
        self._emulator_combo.grid(row=row, column=1, sticky="w", padx=5, pady=5)

        row += 1
        ctk.CTkLabel(section, text="ADB地址:").grid(row=row, column=0, sticky="e", padx=(15, 5), pady=5)
        self._host_entry = ctk.CTkEntry(section, width=250)
        self._host_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)

        row += 1
        ctk.CTkLabel(section, text="ADB端口:").grid(row=row, column=0, sticky="e", padx=(15, 5), pady=5)
        self._port_entry = ctk.CTkEntry(section, width=250)
        self._port_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)

        row += 1
        ctk.CTkLabel(section, text="设备序列:").grid(row=row, column=0, sticky="e", padx=(15, 5), pady=5)
        self._serial_entry = ctk.CTkEntry(section, width=250)
        self._serial_entry.grid(row=row, column=1, sticky="w", padx=5, pady=5)
        ctk.CTkLabel(section, text="留空自动检测", text_color="gray").grid(row=row, column=2, sticky="w", padx=5)

        # 测试连接按钮 + 诊断信息
        row += 1
        test_frame = ctk.CTkFrame(section, fg_color="transparent")
        test_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=15, pady=(15, 5))

        ctk.CTkButton(test_frame, text="测试连接", width=100, command=self._test_connection).pack(side="left")

        self._diag_frame = ctk.CTkFrame(test_frame, fg_color="transparent")
        self._diag_frame.pack(side="left", padx=15)

        self._status_dot = ctk.CTkLabel(self._diag_frame, text="● 未测试", text_color="gray")
        self._status_dot.pack(side="left")
        self._diag_detail = ctk.CTkLabel(self._diag_frame, text="", text_color="gray")
        self._diag_detail.pack(side="left", padx=10)

        # 诊断详情（第二行）
        row += 1
        self._diag_extra = ctk.CTkLabel(section, text="", text_color="gray")
        self._diag_extra.grid(row=row, column=0, columnspan=3, sticky="w", padx=15, pady=(0, 5))

        # 保存并应用按钮
        row += 1
        ctk.CTkButton(section, text="保存并应用", width=120, command=self._save_and_apply).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=15, pady=(10, 15)
        )

    def _load_profiles(self):
        profiles = self.config_mgr.get_adb_profiles()
        names = [p.get("name", "") for p in profiles]
        active = self.config_mgr.get("adb.active_profile", "")

        self._profile_combo.configure(values=names if names else [""])
        if active in names:
            self._profile_combo.set(active)
        elif names:
            self._profile_combo.set(names[0])

        self._fill_form(self.config_mgr.get_active_adb_profile())

    def _fill_form(self, profile: dict[str, Any]):
        self._name_entry.delete(0, "end")
        self._name_entry.insert(0, profile.get("name", ""))

        emulator = profile.get("emulator", "mumu")
        preset = EMULATOR_PRESETS.get(emulator, EMULATOR_PRESETS["custom"])
        self._emulator_combo.set(preset["label"])

        self._host_entry.delete(0, "end")
        self._host_entry.insert(0, profile.get("host", "127.0.0.1"))

        self._port_entry.delete(0, "end")
        self._port_entry.insert(0, str(profile.get("port", 5555)))

        self._serial_entry.delete(0, "end")
        self._serial_entry.insert(0, profile.get("device_serial", "") or "")

    def _read_form(self) -> dict[str, Any]:
        serial = self._serial_entry.get().strip()
        return {
            "name": self._name_entry.get().strip(),
            "emulator": self._get_emulator_key(),
            "host": self._host_entry.get().strip(),
            "port": int(self._port_entry.get().strip() or 5555),
            "device_serial": serial or None,
        }

    def _get_emulator_key(self) -> str:
        label = self._emulator_combo.get()
        for key, val in EMULATOR_PRESETS.items():
            if val["label"] == label:
                return key
        return "custom"

    def _on_profile_switch(self, name: str):
        profiles = self.config_mgr.get_adb_profiles()
        for p in profiles:
            if p.get("name") == name:
                self._fill_form(p)
                return

    def _on_emulator_change(self, label: str):
        for key, val in EMULATOR_PRESETS.items():
            if val["label"] == label:
                self._port_entry.delete(0, "end")
                self._port_entry.insert(0, str(val["device_port"]))
                return

    def _new_profile(self):
        dialog = ctk.CTkInputDialog(text="输入配置名称:", title="新建配置")
        name = dialog.get_input()
        if not name:
            return
        profile = {
            "name": name,
            "emulator": "custom",
            "host": "127.0.0.1",
            "port": 5555,
            "device_serial": None,
        }
        self.config_mgr.save_adb_profile(profile)
        self.config_mgr.set_active_adb_profile(name)
        self.config_mgr.save()
        self._load_profiles()

    def _delete_profile(self):
        name = self._name_entry.get().strip()
        if not name:
            return
        profiles = self.config_mgr.get_adb_profiles()
        if len(profiles) <= 1:
            messagebox.showwarning("提示", "至少保留一个配置方案")
            return
        if not messagebox.askyesno("确认删除", f"确定删除配置 \"{name}\" 吗？"):
            return
        self.config_mgr.delete_adb_profile(name)
        self._load_profiles()

    def _test_connection(self):
        self._status_dot.configure(text="● 测试中...", text_color="yellow")
        self._diag_detail.configure(text="")
        self._diag_extra.configure(text="")

        profile = self._read_form()

        def _run():
            if self._adb_plugin:
                result = self._adb_plugin.test_connection(profile)
            else:
                from plugins.adb_connector.plugin import AdbConnectorPlugin
                temp = AdbConnectorPlugin(self.event_bus, profile)
                result = temp.test_connection()
            self.after(0, self._show_test_result, result)

        threading.Thread(target=_run, daemon=True).start()

    def _show_test_result(self, result: dict):
        if result["success"]:
            self._status_dot.configure(text="● 已连接", text_color="green")
            self._diag_detail.configure(text=f"{result['model']}  序列: {result['serial']}")
            self._diag_extra.configure(
                text=f"分辨率: {result['resolution']}  |  ADB版本: {result['adb_version']}  |  延迟: {result['latency_ms']}ms"
            )
        else:
            self._status_dot.configure(text="● 连接失败", text_color="red")
            self._diag_detail.configure(text=result.get("error", "未知错误"))

    def _save_and_apply(self):
        profile = self._read_form()
        if not profile["name"]:
            messagebox.showwarning("提示", "配置名称不能为空")
            return

        self.config_mgr.save_adb_profile(profile)
        self.config_mgr.set_active_adb_profile(profile["name"])
        self.config_mgr.save()

        # 通知 ADB 插件热重连
        if self._adb_plugin:
            self._adb_plugin.reconnect(profile)

        self.event_bus.emit("adb_config_changed", profile)
        messagebox.showinfo("成功", f"配置 \"{profile['name']}\" 已保存并应用")

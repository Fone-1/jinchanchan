"""数据管理页 — 赛季数据浏览、在线更新、切换、删除"""

import threading
import customtkinter as ctk
from tkinter import messagebox
from typing import Any

from core.event_bus import EventBus
from core.config_manager import ConfigManager
from data import fetcher


class DataPage(ctk.CTkFrame):
    def __init__(self, parent, event_bus: EventBus, config_mgr: ConfigManager):
        super().__init__(parent)
        self.event_bus = event_bus
        self.config_mgr = config_mgr
        self._remote_modes: list[dict] = []
        self._local_modes: list[dict] = []
        self._checkboxes: dict[str, ctk.CTkCheckBox] = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # === 顶部：当前赛季 + 切换 ===
        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        ctk.CTkLabel(top, text="赛季数据管理", font=("", 16, "bold")).pack(side="left", padx=15, pady=10)

        self._current_label = ctk.CTkLabel(top, text=f"当前: {self.config_mgr.season}", font=("", 13))
        self._current_label.pack(side="left", padx=15)

        ctk.CTkButton(top, text="刷新列表", width=90, command=self._refresh).pack(side="right", padx=10, pady=10)
        ctk.CTkButton(top, text="切换赛季", width=90, command=self._switch_season).pack(side="right", padx=5, pady=10)

        # === 本地数据概览 ===
        overview = ctk.CTkFrame(self)
        overview.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

        ctk.CTkLabel(overview, text="本地数据概览", font=("", 13, "bold")).pack(anchor="w", padx=15, pady=(10, 5))
        self._overview_label = ctk.CTkLabel(overview, text="加载中...", anchor="w")
        self._overview_label.pack(anchor="w", padx=15, pady=(0, 10))

        # === 可用模式列表 ===
        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=5, pady=(0, 5))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(list_frame, text="可用模式（从官方获取）", font=("", 13, "bold")).grid(
            row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        self._scroll = ctk.CTkScrollableFrame(list_frame)
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._scroll.grid_columnconfigure(0, weight=1)

        # === 底部操作栏 ===
        bottom = ctk.CTkFrame(self)
        bottom.grid(row=3, column=0, sticky="ew", padx=5, pady=(0, 5))

        ctk.CTkButton(bottom, text="全选", width=60, command=self._select_all).pack(side="left", padx=5, pady=10)
        ctk.CTkButton(bottom, text="反选", width=60, command=self._invert_select).pack(side="left", padx=5, pady=10)
        ctk.CTkButton(bottom, text="在线更新选中", width=120, command=self._update_selected).pack(side="left", padx=15, pady=10)
        ctk.CTkButton(bottom, text="删除选中", width=90, fg_color="gray50",
                       command=self._delete_selected).pack(side="left", padx=5, pady=10)

        self._progress_bar = ctk.CTkProgressBar(bottom, width=200)
        self._progress_bar.pack(side="right", padx=10, pady=10)
        self._progress_bar.set(0)

        self._progress_label = ctk.CTkLabel(bottom, text="", width=200, anchor="e")
        self._progress_label.pack(side="right", padx=5, pady=10)

        # 初始加载
        self.after(100, self._refresh)

    def _refresh(self):
        """刷新本地和远程模式列表"""
        self._local_modes = fetcher.get_local_modes()
        self._update_overview()

        # 在后台线程拉取远程列表
        def _fetch():
            try:
                self._remote_modes = fetcher.list_all_modes()
                self.after(0, self._render_list)
            except Exception as e:
                self.after(0, lambda: self._progress_label.configure(text=f"获取失败: {e}"))

        threading.Thread(target=_fetch, daemon=True).start()

    def _update_overview(self):
        current = self.config_mgr.season
        local = {m["dir_name"]: m for m in self._local_modes}
        if current in local:
            m = local[current]
            parts = []
            for key in ["champions", "traits", "items"]:
                cnt = m.get(f"{key}_count", 0)
                label = {"champions": "弈子", "traits": "羁绊", "items": "装备"}[key]
                parts.append(f"{label}: {cnt}")
            self._overview_label.configure(text=f"{m.get('name', '')} ({m.get('version', '')}) — " + "  ".join(parts))
        else:
            self._overview_label.configure(text="当前模式无本地数据")
        self._current_label.configure(text=f"当前: {current}")

    def _render_list(self):
        """渲染模式列表（带勾选框）"""
        for w in self._scroll.winfo_children():
            w.destroy()
        self._checkboxes.clear()

        local_dirs = {m["dir_name"] for m in self._local_modes}
        current = self.config_mgr.season

        for mode in self._remote_modes:
            dir_name = mode["dir_name"]
            has_local = dir_name in local_dirs
            is_current = dir_name == current

            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.grid(sticky="ew", padx=5, pady=2)
            row.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(row, variable=var, text="", width=24)
            cb.grid(row=0, column=0, padx=(5, 10))
            self._checkboxes[dir_name] = var

            label_parts = [
                f"{mode['season']} - {mode['name']}",
                f"(mode{mode['mode']})",
                f"v{mode['version']}",
            ]
            if is_current:
                label_parts.append("[当前]")
            if has_local:
                label_parts.append("[已下载]")

            ctk.CTkLabel(row, text=" ".join(label_parts), anchor="w").grid(row=0, column=1, sticky="w")

    def _get_selected(self) -> list[str]:
        return [name for name, var in self._checkboxes.items() if var.get()]

    def _select_all(self):
        for var in self._checkboxes.values():
            var.set(True)

    def _invert_select(self):
        for var in self._checkboxes.values():
            var.set(not var.get())

    def _switch_season(self):
        selected = self._get_selected()
        if len(selected) != 1:
            messagebox.showwarning("提示", "请选中一个模式进行切换")
            return
        dir_name = selected[0]
        local_dirs = {m["dir_name"] for m in self._local_modes}
        if dir_name not in local_dirs:
            messagebox.showwarning("提示", "该模式尚未下载数据，请先在线更新")
            return
        self.config_mgr.set_season(dir_name)
        self.event_bus.emit("season_changed", dir_name)
        self._update_overview()
        messagebox.showinfo("成功", f"已切换到 {dir_name}")

    def _update_selected(self):
        selected = self._get_selected()
        if not selected:
            messagebox.showwarning("提示", "请勾选要更新的模式")
            return

        # 找到对应的远程模式信息
        to_update = [m for m in self._remote_modes if m["dir_name"] in selected]
        if not to_update:
            return

        self._progress_bar.set(0)
        total = len(to_update)
        done = [0]

        def _do_update():
            for i, mode_info in enumerate(to_update):
                name = f"{mode_info['season']} {mode_info['name']}"

                def progress_cb(step, total_steps, msg, _i=i, _name=name):
                    overall = (_i + step / total_steps) / total
                    self.after(0, lambda: self._progress_bar.set(overall))
                    self.after(0, lambda: self._progress_label.configure(text=f"{_name}: {msg}"))

                try:
                    stats = fetcher.fetch_mode_data(mode_info, progress_cb)
                    done[0] += 1
                except Exception as e:
                    self.after(0, lambda: self._progress_label.configure(text=f"更新失败: {name} - {e}"))

            self.after(0, lambda: self._progress_bar.set(1.0))
            self.after(0, lambda: self._progress_label.configure(text=f"完成，更新了 {done[0]}/{total} 个模式"))
            self.after(0, self._refresh)

        threading.Thread(target=_do_update, daemon=True).start()

    def _delete_selected(self):
        selected = self._get_selected()
        if not selected:
            messagebox.showwarning("提示", "请勾选要删除的模式")
            return

        current = self.config_mgr.season
        if current in selected:
            messagebox.showwarning("提示", "不能删除当前激活的模式")
            return

        names = ", ".join(selected)
        if not messagebox.askyesno("确认删除", f"确定删除以下模式的本地数据？\n{names}"):
            return

        deleted = 0
        for dir_name in selected:
            if fetcher.delete_mode(dir_name):
                deleted += 1

        messagebox.showinfo("删除完成", f"已删除 {deleted} 个模式")
        self._refresh()

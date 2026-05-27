"""决策引擎 MVP — 根据游戏状态和配置决定是否购买商店弈子"""

import logging
from typing import Any

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class DecisionEnginePlugin(BasePlugin):
    name = "decision_engine"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._mode = config.get("mode", "semi_auto")  # semi_auto | full_auto
        self._auto_buy = config.get("auto_buy", True)
        self._target_champions: list[str] = []  # 目标阵容弈子列表
        self._pending_confirm: dict[str, Any] | None = None

        self.event_bus.on("game_state_updated", self._on_game_state)

    def init(self) -> None:
        logger.info("决策引擎初始化完成")

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def set_target_champions(self, names: list[str]) -> None:
        """设置目标阵容弈子列表"""
        self._target_champions = names
        logger.info(f"目标阵容更新: {names}")

    def confirm_action(self) -> None:
        """半自动模式下，用户确认后执行挂起的操作"""
        if self._pending_confirm:
            self.event_bus.emit("action_required", self._pending_confirm)
            self._pending_confirm = None

    def reject_action(self) -> None:
        """半自动模式下，用户拒绝挂起的操作"""
        self._pending_confirm = None

    def _on_game_state(self, state: dict[str, Any]) -> None:
        if not self._running:
            return

        shop = state.get("shop_champions", [])
        if not shop:
            return

        # 决策：哪些商店弈子值得购买
        actions = self._decide_buy(shop)
        for action in actions:
            self._dispatch(action)

    def _decide_buy(self, shop: list[str | None]) -> list[dict[str, Any]]:
        """决定购买哪些商店弈子"""
        actions = []
        if not self._auto_buy:
            return actions

        for slot_idx, champ_name in enumerate(shop):
            if champ_name is None:
                continue
            # 如果在目标阵容中，推荐购买
            if champ_name in self._target_champions:
                actions.append({
                    "type": "buy_champion",
                    "slot": slot_idx,
                    "champion": champ_name,
                    "reason": f"目标阵容弈子: {champ_name}",
                })
        return actions

    def _dispatch(self, action: dict[str, Any]) -> None:
        if self._mode == "full_auto":
            self.event_bus.emit("action_required", action)
        else:
            # 半自动模式：发送到 UI 等待确认
            self._pending_confirm = action
            self.event_bus.emit("action_pending_confirm", action)

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "mode": {
                "type": "choice",
                "default": "semi_auto",
                "choices": ["semi_auto", "full_auto"],
                "label": "自动化模式",
            },
            "auto_buy": {"type": "boolean", "default": True, "label": "自动购买"},
        }

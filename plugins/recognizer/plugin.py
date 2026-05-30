"""图像识别插件 MVP — 识别商店弈子、金币、等级"""

import logging
import re
import time
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

# 金铲铲之战 UI 区域坐标（基于 1280x720 分辨率）
REGIONS = {
    "shop": (307, 580, 695, 122),    # 商店区域 [x, y, w, h] (已校准，去除了左侧购买经验和刷新按钮)
    "gold": (640, 566, 37, 26),      # 金币区域 (已校准，去除了左侧金币图标以避免被误识别为9)
    "level": (229, 567, 35, 22),      # 等级区域
    "stage": (560, 10, 160, 40),     # 阶段区域
    "traits": (0, 50, 180, 450),     # 羁绊区域 (基于 1280x720)
}

# 备战席 9 格中心坐标（1280x720 分辨率）
BENCH_SLOTS = [
    (180, 506), (300, 506), (420, 506),
    (540, 506), (660, 506), (780, 506),
    (900, 506), (1020, 506), (1140, 506),
]

# 棋盘 28 个六边形格子坐标（4行7列呈交错梅花布局，1280x720 分辨率）
BOARD_GRID = []
_rows_config = [
    {"y": 260, "start_x": 420, "spacing": 76.0}, # 第一行
    {"y": 320, "start_x": 382, "spacing": 82.0}, # 第二行
    {"y": 385, "start_x": 340, "spacing": 88.0}, # 第三行
    {"y": 455, "start_x": 298, "spacing": 95.0}, # 第四行
]
for _cfg in _rows_config:
    _row_cells = []
    _y = _cfg["y"]
    _start_x = _cfg["start_x"]
    _spacing = _cfg["spacing"]
    for _col_idx in range(7):
        _x = _start_x + _col_idx * _spacing
        _row_cells.append((int(_x), _y))
    BOARD_GRID.append(_row_cells)


class RecognizerPlugin(BasePlugin):
    name = "recognizer"

    def __init__(self, event_bus, config: dict[str, Any]):
        super().__init__(event_bus, config)
        self._season = config.get("season", "s14")
        self._templates_dir = Path(__file__).parent.parent.parent / "templates" / self._season
        self._champion_templates: dict[str, np.ndarray] = {}  # 灰度模板
        self._emulator_width = config.get("emulator_width", 1280)
        self._emulator_height = config.get("emulator_height", 720)

        # OCR 引擎和缓存数据
        self._ocr = None
        self._champions_list: list[str] = []
        self._champion_set: set[str] = set()  # O(1) 查找
        self._last_gold = 0
        self._last_level = 1

        # 调试模式：保存裁剪区域图片
        self._debug = config.get("debug", False)
        self._debug_dir = Path(__file__).parent.parent.parent / "debug"
        self._debug_count = 0

        # 任务开关状态
        self._task_enabled = False
        self._use_gpu = config.get("use_gpu", True)

        # 棋盘与备战席的逻辑状态追踪 (Logical State Tracking)
        self._bench_state = [None] * 9  # 1x9 数组，空置为 None，占用为 {"name": str, "star": int}
        self._board_state = [[None] * 7 for _ in range(4)]  # 4x7 二维数组

        # 羁绊约束解算需要的数据结构与购买历史
        self._champions_db: dict[str, Any] = {}
        self._traits_list: list[str] = []
        self._traits_db: dict[str, Any] = {}
        self._bought_history: set[str] = set()

        self.event_bus.on("screenshot_ready", self._on_screenshot)
        self.event_bus.on("task_toggled", self._on_task_toggled)
        self.event_bus.on("action_executed", self._on_action_executed)

    def init(self) -> None:
        self._load_templates()
        self._load_champions_list()
        self._load_champions_db()
        self._load_traits_db()
        logger.info(f"图像识别插件初始化完成，已加载 {len(self._champion_templates)} 个模板")

    def start(self) -> None:
        self._running = True
        # 后台线程初始化 OCR，避免卡住 UI 启动
        import threading
        threading.Thread(target=self._init_ocr, daemon=True).start()

    def _init_ocr(self) -> None:
        if self._ocr is not None:
            return
        try:
            from rapidocr_onnxruntime import RapidOCR
            t0 = time.perf_counter()
            if self._use_gpu:
                self._ocr = RapidOCR(det_use_dml=True, cls_use_dml=True, rec_use_dml=True)
                elapsed = time.perf_counter() - t0
                logger.info(f"RapidOCR GPU (DirectML) 引擎初始化成功 ({elapsed:.1f}s)")
            else:
                self._ocr = RapidOCR()
                elapsed = time.perf_counter() - t0
                logger.info(f"RapidOCR CPU 引擎初始化成功 ({elapsed:.1f}s)")
        except Exception as e:
            logger.error(f"初始化 RapidOCR 失败: {e}")

    def _load_champions_list(self) -> None:
        champs_file = Path(__file__).parent.parent.parent / "data" / self._season / "champions.json"
        if champs_file.exists():
            try:
                with open(champs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._champions_list = list(data.keys())
                    self._champion_set = set(self._champions_list)
                logger.info(f"已从 {self._season} 载入 {len(self._champions_list)} 个合法弈子名单进行 OCR 过滤")
            except Exception as e:
                logger.error(f"加载弈子列表失败: {e}")

    def stop(self) -> None:
        self._running = False

    def _on_task_toggled(self, enabled: bool) -> None:
        self._task_enabled = enabled
        logger.info(f"识别任务{'已启动' if enabled else '已停止'}")

    def _on_action_executed(self, data: dict[str, Any]) -> None:
        """根据操作执行器的动作，实时更新棋盘与备战席的逻辑状态 (Logical State Tracking)"""
        if not data.get("success", False):
            return
            
        action = data.get("action", {})
        action_type = action.get("type")
        
        if action_type == "buy_champion":
            champ_name = action.get("champion")
            if champ_name:
                self._bought_history.add(champ_name)
            # 弈子购买成功，自动放入备战席第一个空位上
            for i in range(9):
                if self._bench_state[i] is None:
                    self._bench_state[i] = {"name": champ_name, "star": 1}
                    logger.info(f"[State Tracking] 购买弈子 '{champ_name}'，自动放入备战席 Slot {i}")
                    break
                    
        elif action_type == "sell_champion":
            bench_idx = action.get("bench_index")
            if bench_idx is not None and 0 <= bench_idx < 9:
                old_champ = self._bench_state[bench_idx]
                self._bench_state[bench_idx] = None
                logger.info(f"[State Tracking] 售出备战席 Slot {bench_idx} 上的弈子: {old_champ}")
                
        elif action_type == "move_champion":
            from_pos = action.get("from")
            to_pos = action.get("to")
            if from_pos and to_pos:
                # from_pos, to_pos 是 1280x720 下的 (X, Y) 坐标
                from_res = self._map_coords_to_grid(from_pos[0], from_pos[1])
                to_res = self._map_coords_to_grid(to_pos[0], to_pos[1])
                if from_res and to_res:
                    from_type, from_idx = from_res
                    to_type, to_idx = to_res
                    
                    # 提取起始位置的弈子
                    from_item = None
                    if from_type == "bench":
                        from_item = self._bench_state[from_idx]
                        self._bench_state[from_idx] = None
                    elif from_type == "board":
                        from_item = self._board_state[from_idx[0]][from_idx[1]]
                        self._board_state[from_idx[0]][from_idx[1]] = None
                        
                    # 提取目标位置的弈子（用于对调）
                    to_item = None
                    if to_type == "bench":
                        to_item = self._bench_state[to_idx]
                        self._bench_state[to_idx] = from_item
                    elif to_type == "board":
                        to_item = self._board_state[to_idx[0]][to_idx[1]]
                        self._board_state[to_idx[0]][to_idx[1]] = from_item
                        
                    # 放回对调弈子
                    if from_type == "bench":
                        self._bench_state[from_idx] = to_item
                    elif from_type == "board":
                        self._board_state[from_idx[0]][from_idx[1]] = to_item
                        
                    logger.info(f"[State Tracking] 移动对调: {from_res} ({from_item}) <-> {to_res} ({to_item})")

    def _map_coords_to_grid(self, x: int, y: int) -> tuple[str, Any] | None:
        """将屏幕 1280x720 坐标映射为具体的备战席索引或棋盘格子坐标"""
        # 1. 检查是否在备战席格子内 (距离 <= 60px)
        for idx, (bx, by) in enumerate(BENCH_SLOTS):
            if abs(x - bx) < 60 and abs(y - by) < 40:
                return "bench", idx
                
        # 2. 检查是否在棋盘格子内 (距离最小的格子)
        best_cell = None
        min_dist = 60
        for r_idx, row in enumerate(BOARD_GRID):
            for c_idx, (gx, gy) in enumerate(row):
                dist = np.hypot(x - gx, y - gy)
                if dist < min_dist:
                    min_dist = dist
                    best_cell = ("board", (r_idx, c_idx))
                    
        if best_cell:
            return best_cell
        return None

    def _load_templates(self) -> None:
        """加载模板并预处理为灰度图，避免运行时重复转换"""
        champ_dir = self._templates_dir / "champions"
        if not champ_dir.exists():
            logger.warning(f"模板目录不存在: {champ_dir}")
            return
        for img_path in champ_dir.glob("*.png"):
            name = img_path.stem
            tpl = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if tpl is not None:
                self._champion_templates[name] = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)

    def _on_screenshot(self, img: np.ndarray) -> None:
        if not self._running or not self._task_enabled:
            return
        game_state = self._analyze(img)
        if game_state:
            self.event_bus.emit("game_state_updated", game_state)

    def _analyze(self, img: np.ndarray) -> dict[str, Any] | None:
        t_start = time.perf_counter()

        prev_level = self._last_level

        h, w = img.shape[:2]
        scale_x = w / self._emulator_width
        scale_y = h / self._emulator_height

        # 调试模式：保存裁剪区域
        if self._debug and self._debug_count < 3:
            self._save_debug_regions(img, scale_x, scale_y)

        gold, level, shop_champions = self._recognize_all(img, scale_x, scale_y)

        # 自动重置逻辑：如果检测到的等级比上次明显降低（如从后期重归1-3级），说明新开了一局，需清空旧棋盘历史，防旧子残留
        if level < prev_level and level <= 3:
            logger.info(f"[New Game Detected] 等级由 {prev_level} 级下降至 {level} 级，自动清空历史购买和棋盘/备战席数据")
            self._bench_state = [None] * 9
            self._board_state = [[None] * 7 for _ in range(4)]
            self._bought_history.clear()

        # 视觉检测棋盘格子占用情况 (血条检测)
        board_occupied = self._detect_board_occupancy(img, scale_x, scale_y)
        
        # 视觉检测备战席占用情况 (根据图像特征的简易辅助判定)
        bench_occupied = self._detect_bench_occupancy(img, scale_x, scale_y)
        
        # 混合融合：使用视觉占用对逻辑追踪状态进行校准
        self._sync_states(board_occupied, bench_occupied)

        # 羁绊约束解算：尝试将 "在场弈子" 解析为具体弈子名称
        self._resolve_placeholders(img, scale_x, scale_y)

        # 调试模式增加计数
        if self._debug and self._debug_count < 3:
            self._debug_count += 1

        elapsed = time.perf_counter() - t_start
        logger.info(f"识别完成: {elapsed:.2f}s | 金币={gold} 等级={level} 商店={shop_champions}")

        state = {
            "gold": gold,
            "level": level,
            "shop_champions": shop_champions,
            "bench_state": self._bench_state.copy(),
            "board_state": [row.copy() for row in self._board_state],
            "raw_image": img,
        }
        return state

    def _detect_board_occupancy(self, img: np.ndarray, sx: float, sy: float) -> list[list[bool]]:
        """利用亮绿色生命值血条的 HSV 特征和几何轮廓过滤，检测 28 个棋盘格子的占用状态"""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_green = np.array([48, 130, 150])
        upper_green = np.array([68, 255, 255])
        mask = cv2.inRange(hsv, lower_green, upper_green)
        
        board_occupied = [[False] * 7 for _ in range(4)]
        
        for r_idx, row in enumerate(BOARD_GRID):
            for c_idx, (gx, gy) in enumerate(row):
                cx_scaled = int(gx * sx)
                cy_scaled = int(gy * sy)
                
                y1 = max(0, int(cy_scaled - 40 * sy))
                y2 = min(img.shape[0], int(cy_scaled + 20 * sy))
                x1 = max(0, int(cx_scaled - 40 * sx))
                x2 = min(img.shape[1], int(cx_scaled + 40 * sx))
                
                roi_mask = mask[y1:y2, x1:x2]
                contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for cnt in contours:
                    _, _, w_cnt, h_cnt = cv2.boundingRect(cnt)
                    w_720 = w_cnt / sx
                    h_720 = h_cnt / sy
                    aspect_ratio = w_720 / h_720 if h_720 > 0 else 0
                    
                    # 几何尺寸过滤：宽度 [12, 65]，高度 [2.5, 12]，长宽比 >= 1.5
                    if 12 <= w_720 <= 65 and 2.5 <= h_720 <= 12 and aspect_ratio >= 1.5:
                        board_occupied[r_idx][c_idx] = True
                        break
                     
        return board_occupied

    def _detect_bench_occupancy(self, img: np.ndarray, sx: float, sy: float) -> list[bool]:
        """视觉检测备战席格子的占用情况"""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bench_occupied = [False] * 9
        
        for idx, (bx, by) in enumerate(BENCH_SLOTS):
            cx_scaled = int(bx * sx)
            cy_scaled = int(by * sy)
            
            y1 = max(0, int(cy_scaled - 20 * sy))
            y2 = min(img.shape[0], int(cy_scaled + 20 * sy))
            x1 = max(0, int(cx_scaled - 30 * sx))
            x2 = min(img.shape[1], int(cx_scaled + 30 * sx))
            
            roi = gray[y1:y2, x1:x2]
            std = np.std(roi)
            
            # 空槽的标准差极小；有棋子时标准差通常 > 16.0
            if std > 16.0:
                bench_occupied[idx] = True
                 
        return bench_occupied

    def _sync_states(self, board_occupied: list[list[bool]], bench_occupied: list[bool]) -> None:
        """结合视觉物理占用，校准逻辑状态追踪"""
        # 1. 校准棋盘格子
        for r in range(4):
            for c in range(7):
                is_occupied = board_occupied[r][c]
                logical_item = self._board_state[r][c]
                
                if not is_occupied:
                    # 视觉显示没有棋子（血条消失了，比如战斗死亡或手动卖出/移动）
                    if logical_item is not None:
                        self._board_state[r][c] = None
                        logger.info(f"[State Sync] 棋盘 ({r},{c}) 视觉显示为空，自动清除逻辑状态: {logical_item}")
                else:
                    # 视觉显示有棋子，但逻辑状态为空（可能是手动放上去的，或动作丢失）
                    if logical_item is None:
                        self._board_state[r][c] = {"name": "在场弈子", "star": 1}
                        logger.info(f"[State Sync] 棋盘 ({r},{c}) 视觉显示有棋子，自动填充逻辑占位")
                         
        # 2. 校准备战席
        for idx in range(9):
             is_occupied = bench_occupied[idx]
             logical_item = self._bench_state[idx]
             
             if not is_occupied and logical_item is not None:
                 # 备战席格子上视觉是空的，清除逻辑状态
                 self._bench_state[idx] = None
                 logger.info(f"[State Sync] 备战席 Slot {idx} 视觉显示为空，自动清除逻辑状态: {logical_item}")

    def _save_debug_regions(self, img: np.ndarray, sx: float, sy: float) -> None:
        """保存裁剪区域图片用于调试"""
        self._debug_dir.mkdir(exist_ok=True)
        for region_key in ["gold", "level", "shop"]:
            roi = self._crop_region(img, region_key, sx, sy)
            path = self._debug_dir / f"{region_key}_{self._debug_count}.png"
            cv2.imwrite(str(path), roi)
            logger.info(f"[DEBUG] 保存裁剪区域: {path} (尺寸: {roi.shape})")
        cv2.imwrite(str(self._debug_dir / f"full_{self._debug_count}.png"), img)
        logger.info(f"[DEBUG] 调试图片已保存到 {self._debug_dir}")

    def _crop_region(self, img: np.ndarray, region_key: str, sx: float, sy: float) -> np.ndarray:
        x, y, rw, rh = REGIONS[region_key]
        x1, y1 = int(x * sx), int(y * sy)
        x2, y2 = int((x + rw) * sx), int((y + rh) * sy)
        return img[y1:y2, x1:x2]

    def _recognize_all(self, img: np.ndarray, sx: float, sy: float) -> tuple[int, int, list[str | None]]:
        """水平拼接金币、等级和商店区域，进行单次 OCR 识别以大幅提升速度与准确率"""
        if self._ocr is None:
            return self._last_gold, self._last_level, [None] * 5

        # 1. 裁剪并转换为灰度图以减少色彩通道干扰
        gold_roi = self._crop_region(img, "gold", sx, sy)
        level_roi = self._crop_region(img, "level", sx, sy)
        shop_roi = self._crop_region(img, "shop", sx, sy)

        gold_gray = cv2.cvtColor(gold_roi, cv2.COLOR_BGR2GRAY)
        level_gray = cv2.cvtColor(level_roi, cv2.COLOR_BGR2GRAY)

        # 提取 5 个商店卡槽的名字区域
        shop_h, shop_w = shop_roi.shape[:2]
        slot_w = shop_w // 5
        name_rois = []

        target_height = 96  # 统一拉伸高度，保证 OCR 字符足够大且清晰

        for i in range(5):
            slot = shop_roi[:, i * slot_w:(i + 1) * slot_w]
            sh, sw = slot.shape[:2]
            y1, y2 = int(sh * 0.70), int(sh * 0.99)
            x1, x2 = int(sw * 0.05), int(sw * 0.95)
            name_roi = slot[y1:y2, x1:x2]
            name_gray = cv2.cvtColor(name_roi, cv2.COLOR_BGR2GRAY)

            # 缩放到统一高度
            nh, nw = name_gray.shape[:2]
            if nh != target_height:
                scale = target_height / nh
                name_gray = cv2.resize(name_gray, (int(nw * scale), target_height), interpolation=cv2.INTER_CUBIC)
            name_rois.append(name_gray)

        # 缩放金币和等级到统一高度
        gh, gw = gold_gray.shape[:2]
        gold_resized = cv2.resize(gold_gray, (int(gw * (target_height / gh)), target_height), interpolation=cv2.INTER_CUBIC)

        lh, lw = level_gray.shape[:2]
        level_resized = cv2.resize(level_gray, (int(lw * (target_height / lh)), target_height), interpolation=cv2.INTER_CUBIC)

        # 黑色拼接缓冲块，用于把各字符区块隔开，避免 OCR 把相邻文本融为一体，并解决边缘文本识别不准的问题
        spacer_width = 40
        spacer = np.zeros((target_height, spacer_width), dtype=np.uint8)

        parts = []
        intervals = []
        current_x = 0

        def append_spacer():
            nonlocal current_x
            parts.append(spacer)
            current_x += spacer_width

        def append_part(part_img, name):
            nonlocal current_x
            parts.append(part_img)
            w = part_img.shape[1]
            intervals.append({
                "name": name,
                "start_x": current_x,
                "end_x": current_x + w
            })
            current_x += w

        # 依次拼接：[边缘缓冲] [金币] [缓冲] [等级] [缓冲] [卡槽0] ... [卡槽4] [边缘缓冲]
        append_spacer()
        append_part(gold_resized, "gold")
        append_spacer()
        append_part(level_resized, "level")
        append_spacer()
        for i in range(5):
            append_part(name_rois[i], f"slot_{i}")
            append_spacer()

        stitched_img = np.hstack(parts)
        stitched_bgr = cv2.cvtColor(stitched_img, cv2.COLOR_GRAY2BGR)

        # 调试模式下保存拼接大图
        if self._debug and self._debug_count < 3:
            self._debug_dir.mkdir(exist_ok=True)
            path = self._debug_dir / f"stitched_{self._debug_count}.png"
            cv2.imwrite(str(path), stitched_bgr)
            logger.info(f"[DEBUG] 保存拼接后大图: {path}")

        try:
            ocr_res, _ = self._ocr(stitched_bgr)
        except Exception as e:
            logger.error(f"OCR 引擎识别拼接图出错: {e}")
            return self._last_gold, self._last_level, [None] * 5

        parsed_results = {
            "gold": "",
            "level": "",
            "slot_0": "",
            "slot_1": "",
            "slot_2": "",
            "slot_3": "",
            "slot_4": "",
        }

        # 根据检测框的中心 X 坐标落入哪个原图区间，把识别结果分派给对应的变量
        if ocr_res:
            for box, text, score in ocr_res:
                pts = np.array(box)
                center_x = np.mean(pts[:, 0])
                for interval in intervals:
                    if interval["start_x"] <= center_x <= interval["end_x"]:
                        name = interval["name"]
                        if name in ["gold", "level"]:
                            parsed_results[name] += text
                        else:
                            cleaned = re.sub(r"[^一-龥]", "", text)
                            if cleaned:
                                parsed_results[name] += cleaned
                        break

        # 3. 提取并校正字段
        # 金币
        gold_text = parsed_results["gold"]
        gold_str = re.sub(r"\D", "", gold_text)
        if gold_str:
            self._last_gold = int(gold_str)
        logger.info(f"Gold OCR: '{gold_text}' -> {self._last_gold}")

        # 等级
        level_text = parsed_results["level"]
        level_str = re.sub(r"\D", "", level_text)
        if level_str:
            val = int(level_str)
            if 1 <= val <= 10:
                self._last_level = val
        logger.info(f"Level OCR: '{level_text}' -> {self._last_level}")

        # 商店弈子匹配（引入模糊匹配和头像模板匹配兜底）
        shop_champions = []
        for i in range(5):
            raw_text = parsed_results[f"slot_{i}"]
            champ_name = self._match_champion_name(raw_text)
            if not champ_name:
                # 如果 OCR 没识别到任何合法内容，尝试模板匹配头像进行兜底
                slot_img = shop_roi[:, i * slot_w:(i + 1) * slot_w]
                champ_name = self._match_champion(slot_img)
            shop_champions.append(champ_name)

        return self._last_gold, self._last_level, shop_champions

    def _match_champion_name(self, text: str) -> str | None:
        """将 OCR 文字匹配到合法弈子名（支持基于字符交集的模糊相似度匹配）"""
        if not text:
            return None
        if text in self._champion_set:
            return text
        
        # 1. 优先尝试子串包含匹配
        for champ in self._champions_list:
            if champ in text or text in champ:
                return champ
                
        # 2. 相似度模糊匹配（交集字数 / max(识别长度, 真实长度)）
        best_champ = None
        best_score = 0.0
        
        text_chars = set(text)
        for champ in self._champions_list:
            champ_chars = set(champ)
            intersection = text_chars.intersection(champ_chars)
            if not intersection:
                continue
            
            score = len(intersection) / max(len(text), len(champ))
            if score > best_score:
                best_score = score
                best_champ = champ
                
        # 阈值设为 0.5（2字名字错1个字或3字名字错1个字均可匹配）
        if best_score >= 0.5:
            logger.info(f"Fuzzy Match: '{text}' -> '{best_champ}' (score: {best_score:.2f})")
            return best_champ
            
        return None

    def _match_champion(self, slot_img: np.ndarray) -> str | None:
        """模板匹配商店弈子头像（模板已预处理为灰度）"""
        if not self._champion_templates:
            return None
        best_name = None
        best_score = 0.0
        slot_gray = cv2.cvtColor(slot_img, cv2.COLOR_BGR2GRAY)
        for name, tpl_gray in self._champion_templates.items():
            if tpl_gray.shape[0] > slot_gray.shape[0] or tpl_gray.shape[1] > slot_gray.shape[1]:
                continue
            res = cv2.matchTemplate(slot_gray, tpl_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best_score:
                best_score = max_val
                best_name = name
        if best_score > 0.7:
            return best_name
        return None

    def _load_champions_db(self) -> None:
        champs_file = Path(__file__).parent.parent.parent / "data" / self._season / "champions.json"
        if champs_file.exists():
            try:
                with open(champs_file, "r", encoding="utf-8") as f:
                    self._champions_db = json.load(f)
                logger.info(f"已从 {self._season} 载入 {len(self._champions_db)} 个弈子属性属性库")
            except Exception as e:
                logger.error(f"加载弈子属性属性库失败: {e}")
                self._champions_db = {}
        else:
            self._champions_db = {}

    def _load_traits_db(self) -> None:
        traits_file = Path(__file__).parent.parent.parent / "data" / self._season / "traits.json"
        if traits_file.exists():
            try:
                with open(traits_file, "r", encoding="utf-8") as f:
                    self._traits_db = json.load(f)
                    self._traits_list = list(self._traits_db.keys())
                logger.info(f"已从 {self._season} 载入 {len(self._traits_list)} 个合法羁绊名单")
            except Exception as e:
                logger.error(f"加载羁绊列表失败: {e}")
                self._traits_list = []
                self._traits_db = {}
        else:
            self._traits_list = []
            self._traits_db = {}

    def _match_trait_name(self, text: str) -> str | None:
        if not text:
            return None
        if text in self._traits_list:
            return text
        for trait in self._traits_list:
            if trait in text or text in trait:
                return trait
        best_trait = None
        best_score = 0.0
        text_chars = set(text)
        for trait in self._traits_list:
            trait_chars = set(trait)
            intersection = text_chars.intersection(trait_chars)
            if not intersection:
                continue
            score = len(intersection) / max(len(text), len(trait))
            if score > best_score:
                best_score = score
                best_trait = trait
        if best_score >= 0.5:
            return best_trait
        return None

    def _parse_active_traits(self, left_ocr_res: list) -> dict[str, int]:
        active_traits = {}
        sorted_res = sorted(left_ocr_res, key=lambda item: np.min(np.array(item[0])[:, 1]))
        i = 0
        while i < len(sorted_res):
            box, text, score = sorted_res[i]
            text = text.strip()
            matched_trait = None
            for trait in self._traits_list:
                if trait in text:
                    matched_trait = trait
                    break
            if not matched_trait:
                matched_trait = self._match_trait_name(text)
            if matched_trait:
                count = None
                rem_text = text.replace(matched_trait, "")
                nums = re.findall(r"\d+", rem_text)
                if nums:
                    count = int(nums[0])
                else:
                    if i + 1 < len(sorted_res):
                        next_box, next_text, next_score = sorted_res[i+1]
                        nums = re.findall(r"\d+", next_text)
                        if nums:
                            count = int(nums[0])
                            i += 1
                if count is None:
                    count = 1
                active_traits[matched_trait] = count
            i += 1
        return active_traits

    def _resolve_placeholders(self, img: np.ndarray, sx: float, sy: float) -> None:
        placeholders = []
        for r in range(4):
            for c in range(7):
                item = self._board_state[r][c]
                if item and item.get("name") == "在场弈子":
                    placeholders.append((r, c))
        if not placeholders:
            return

        # 1. 裁剪并 OCR 羁绊区域
        traits_roi = self._crop_region(img, "traits", sx, sy)
        if self._ocr is None:
            return
        try:
            ocr_res, _ = self._ocr(traits_roi)
        except Exception as e:
            logger.error(f"OCR 识别羁绊区域出错: {e}")
            return
        if not ocr_res:
            logger.info("[Synergy Solver] 羁绊区域未检测到任何文本，保持在场占位")
            return

        # 2. 解析羁绊
        observed_traits = self._parse_active_traits(ocr_res)
        if not observed_traits:
            return
        logger.info(f"[Synergy Solver] 识别到左侧活跃羁绊: {observed_traits}")

        # 3. 统计当前棋盘上已知的弈子名字
        identified_champs = []
        for r in range(4):
            for c in range(7):
                item = self._board_state[r][c]
                if item and item.get("name") and item["name"] != "在场弈子":
                    identified_champs.append(item["name"])

        # 4. 计算缺失的羁绊计数
        missing_traits = {}
        for trait, count in observed_traits.items():
            id_count = 0
            for name in identified_champs:
                champ_info = self._champions_db.get(name, {})
                if champ_info.get("race") == trait or champ_info.get("job") == trait:
                    id_count += 1
            missing = count - id_count
            if missing > 0:
                missing_traits[trait] = missing

        logger.info(f"[Synergy Solver] 需要补全的羁绊差额: {missing_traits}")

        # 5. 编译候选候选池 (Bench 已经拥有的弈子 + 购买历史)
        owned_candidates = set()
        for item in self._bench_state:
            if item and item.get("name") and item["name"] != "在场弈子":
                owned_candidates.add(item["name"])
        for name in self._bought_history:
            if name != "在场弈子":
                owned_candidates.add(name)

        # 收集目前拥有或见过的所有弈子以补充历史库（防御可能丢失的购买事件）
        for r in range(4):
            for c in range(7):
                item = self._board_state[r][c]
                if item and item.get("name") and item["name"] != "在场弈子":
                    self._bought_history.add(item["name"])
                    owned_candidates.add(item["name"])

        global_candidates = list(self._champions_db.keys())

        # 6. 对每个占位符进行最优化匹配
        for r, c in placeholders:
            best_champ = None
            best_score = -1
            best_source = ""

            for name in global_candidates:
                champ_info = self._champions_db.get(name, {})
                cost = champ_info.get("cost", 1)

                # 如果该弈子玩家并没有购买记录/备战记录，利用玩家当前等级进行费用过滤限制
                if name not in owned_candidates:
                    current_level = self._last_level
                    if current_level <= 2 and cost > 1:
                        continue
                    if current_level <= 4 and cost > 2:
                        continue
                    if current_level <= 6 and cost > 3:
                        continue

                # 计算该候选弈子能满足多少缺失的羁绊
                ts_score = 0
                race = champ_info.get("race")
                job = champ_info.get("job")
                if race in missing_traits:
                    ts_score += 1
                if job in missing_traits:
                    ts_score += 1

                # 设定来源优先级：Bench > 历史已买 > 全局符合等级低费弈子
                priority = 0
                source = "global"
                if name in self._bought_history:
                    priority = 10
                    source = "history"
                is_on_bench = any(item and item.get("name") == name for item in self._bench_state)
                if is_on_bench:
                    priority = 20
                    source = "bench"

                total_score = ts_score * 100 + priority

                if total_score > best_score:
                    best_score = total_score
                    best_champ = name
                    best_source = source

            if best_champ and best_score > 0:
                logger.info(f"[Synergy Solver] 解析占位成功: 棋盘 ({r},{c}) -> '{best_champ}' (来源: {best_source}, 评分: {best_score})")
                self._board_state[r][c] = {"name": best_champ, "star": 1}
                
                # 扣减该弈子带来的羁绊差额贡献
                champ_info = self._champions_db.get(best_champ, {})
                race = champ_info.get("race")
                job = champ_info.get("job")
                if race in missing_traits:
                    missing_traits[race] -= 1
                    if missing_traits[race] <= 0:
                        del missing_traits[race]
                if job in missing_traits:
                    missing_traits[job] -= 1
                    if missing_traits[job] <= 0:
                        del missing_traits[job]
            else:
                logger.warning(f"[Synergy Solver] 棋盘 ({r},{c}) 占位未能匹配到合适的弈子")

    def get_debug_info(self) -> dict[str, Any]:
        return {
            "season": self._season,
            "templates_loaded": len(self._champion_templates),
            "champions_list_size": len(self._champions_list),
            "ocr_ready": self._ocr is not None,
            "last_gold": self._last_gold,
            "last_level": self._last_level,
            "task_enabled": self._task_enabled,
            "debug_mode": self._debug,
            "debug_images_saved": self._debug_count,
            "bench_state": self._bench_state,
            "board_state": self._board_state,
        }

    @staticmethod
    def get_config_schema() -> dict[str, Any]:
        return {
            "emulator_width": {"type": "integer", "default": 1280, "label": "模拟器宽度"},
            "emulator_height": {"type": "integer", "default": 720, "label": "模拟器高度"},
            "use_gpu": {"type": "boolean", "default": True, "label": "启用 GPU 加速 (DirectML)"},
            "debug": {"type": "boolean", "default": False, "label": "调试模式（保存裁剪区域图片）"},
        }

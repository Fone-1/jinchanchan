"""金铲铲之战官方数据拉取模块"""

from data.fetcher._local import get_local_modes, fetch_mode_data, delete_mode
from data.fetcher._remote import list_all_modes

__all__ = ["get_local_modes", "list_all_modes", "fetch_mode_data", "delete_mode"]

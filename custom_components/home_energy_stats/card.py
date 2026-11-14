"""Home Energy Stats 的 Lovelace 卡片資源註冊。

必須走**兩條通道**，否則 YAML mode / storage mode 會有一邊失效：
  1. Lovelace resource（res_type: module）
  2. frontend extra_module_url

資源集合用 duck typing 取得：`hass.data["lovelace"]` 舊版是 dict、
新版是 dataclass，能不能寫入用 `hasattr(resources, "async_create_item")` 判斷，
不要用 isinstance（collection 的類別跨 HA 版本會變）。
"""

from __future__ import annotations

import logging

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "home-energy-stats-card.js"
CARD_URL = f"/home_energy_stats/{CARD_FILENAME}"
CARD_VERSION = "1.0.0"


def _get_resources(hass: HomeAssistant):
    """取得 Lovelace 資源集合（duck typing）。"""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    return resources


async def async_register_card(hass: HomeAssistant) -> None:
    """註冊卡片資源。"""
    # 通道 2：frontend extra_module_url
    try:
        add_extra_js_url(hass, CARD_URL, es5=False)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("add_extra_js_url 失敗（可能重複註冊）：%s", err)

    # 通道 1：Lovelace resource
    resources = _get_resources(hass)
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.debug("Lovelace resources 尚未就緒，稍後由 reload_card 服務補註冊")
        return

    for item in resources.async_items():
        if item.get("url") == CARD_URL:
            # 已存在就更新版本，避免重複
            if item.get("res_type") != "module":
                await resources.async_update_item(
                    item["id"], {"res_type": "module"}
                )
            return

    await resources.async_create_item(
        {"res_type": "module", "url": f"{CARD_URL}?v={CARD_VERSION}"}
    )
    _LOGGER.info("已註冊 Lovelace 卡片資源：%s", CARD_URL)

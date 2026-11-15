"""Home Energy Stats 的 Lovelace 卡片資源註冊。

首次啟動鏈有五層，前一層不通時使用者只會看到最外層的症狀
（`Custom element doesn't exist`）。這裡把每一層都處理好：

  1. 整合 setup
  2. **靜態路徑註冊** ← 沒有這層，JS 檔會 404，瀏覽器拿不到程式碼
  3. 卡片 JS 的 customElements 註冊
  4. Lovelace 資源註冊（要兩條通道）
  5. 卡片設定解析出來源

實測教訓（v1.0.2 → v1.0.3）：
- 開機時 `hass.http` 已經就緒，但整合 setup 的時機仍可能太早。
  所以除了 setup 當下註冊，還要**在 HA 完全啟動後再補一次**。
- 資源集合用 duck typing 取得：`hass.data["lovelace"]` 舊版是 dict、
  新版是 dataclass，能不能寫入用 `hasattr(resources, "async_create_item")` 判斷，
  不要用 isinstance（collection 的類別跨 HA 版本會變）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "home-energy-stats-card.js"
CARD_VERSION = "1.0.3"
# 靜態路徑前綴。必須跟整合 domain 一致，且不要跟其他整合重疊。
STATIC_URL_PATH = "/home_energy_stats"
CARD_URL = f"{STATIC_URL_PATH}/{CARD_FILENAME}"

# 記錄已註冊的 extra module url，避免同一支檔案被載入兩次
DATA_EXTRA_MODULES = "home_energy_stats_extra_modules"
# 標記靜態路徑是否已註冊，避免重複註冊
DATA_STATIC_REGISTERED = "home_energy_stats_static_registered"


def _get_resources(hass: HomeAssistant):
    """取得 Lovelace 資源集合（duck typing）。"""
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return None
    resources = getattr(lovelace, "resources", None)
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    return resources


async def async_register_static_path(hass: HomeAssistant) -> bool:
    """註冊卡片 JS 的靜態路徑。

    **沒有這一步，`/home_energy_stats/home-energy-stats-card.js` 會 404**，
    前端就會報 `Custom element doesn't exist`。

    回傳 True 表示註冊成功。
    """
    if hass.data.get(DATA_STATIC_REGISTERED):
        return True

    www_dir = Path(__file__).parent / "www"
    if not (www_dir / CARD_FILENAME).exists():
        _LOGGER.error("卡片檔不存在：%s", www_dir / CARD_FILENAME)
        return False

    http = getattr(hass, "http", None)
    if http is None:
        _LOGGER.warning("hass.http 尚未就緒，稍後重試註冊靜態路徑")
        return False

    try:
        from homeassistant.components.http import StaticPathConfig

        await http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, str(www_dir), True)]
        )
    except ImportError:
        # HA 2024.7 以下
        try:
            http.register_static_path(STATIC_URL_PATH, str(www_dir))
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("註冊靜態路徑失敗：%s", err)
            return False
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("註冊靜態路徑失敗：%s", err)
        return False

    hass.data[DATA_STATIC_REGISTERED] = True
    _LOGGER.info("已註冊靜態路徑 %s → %s", STATIC_URL_PATH, www_dir)
    return True


def _add_extra_module(hass: HomeAssistant, url: str) -> None:
    """註冊 extra_module_url，並移除同一支檔案的舊版本。

    只保留最新一份：同一個檔案用兩個不同 url 會被載入兩次。
    """
    known = hass.data.setdefault(DATA_EXTRA_MODULES, set())
    base = url.split("?")[0]

    for old in list(known):
        if old == url or old.split("?")[0] != base:
            continue
        try:
            from homeassistant.components.frontend import remove_extra_js_url

            remove_extra_js_url(hass, old)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("無法移除舊的 module url %s", old)
        known.discard(old)

    try:
        add_extra_js_url(hass, url)
    except KeyError:
        # frontend 還沒 setup 完
        _LOGGER.debug("Frontend 尚未就緒，略過 extra module url")
        return
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("註冊 extra module url 失敗：%s", err)
        return

    known.add(url)


async def async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """註冊 Lovelace 資源（storage mode 用的那一條通道）。"""
    resources = _get_resources(hass)
    if resources is None or not hasattr(resources, "async_create_item"):
        _LOGGER.debug("Lovelace resources 尚未就緒，之後用 reload_card 服務補註冊")
        return

    url = f"{CARD_URL}?v={CARD_VERSION}"
    existing = None
    for item in resources.async_items():
        # 比對「去掉 query 的路徑」，這樣 ?v= 改版時才抓得到舊的那筆
        if item.get("url", "").split("?")[0] == CARD_URL:
            existing = item
            break

    if existing is not None:
        if existing.get("url") == url and existing.get("res_type") == "module":
            return  # 已經是正確的，不動它
        await resources.async_update_item(
            existing["id"], {"url": url, "res_type": "module"}
        )
        _LOGGER.info("已更新 Lovelace 卡片資源：%s", url)
        return

    await resources.async_create_item({"res_type": "module", "url": url})
    _LOGGER.info("已註冊 Lovelace 卡片資源：%s", url)


async def async_register_card(hass: HomeAssistant) -> None:
    """註冊卡片資源（靜態路徑 + 兩條通道）。"""
    ok = await async_register_static_path(hass)
    if not ok:
        # 稍後重試：HA 完全啟動後 http 與 lovelace 才真的可用
        async_call_later(hass, 30, _async_retry_register)

    # 通道 2：frontend extra_module_url（YAML mode 與 safety net）
    _add_extra_module(hass, f"{CARD_URL}?v={CARD_VERSION}")

    # 通道 1：Lovelace resource（storage mode）
    await async_register_lovelace_resource(hass)


async def _async_retry_register(hass: HomeAssistant) -> None:
    """延遲後重試註冊（開機時機太早的保險）。"""
    ok = await async_register_static_path(hass)
    if ok:
        await async_register_lovelace_resource(hass)
        _LOGGER.info("延遲重試：卡片資源註冊完成")
    else:
        _LOGGER.warning("延遲重試仍無法註冊靜態路徑，請手動呼叫 home_energy_stats.reload_card")


async def async_setup_card(hass: HomeAssistant, _event: Event | None = None) -> None:
    """HA 完全啟動後再註冊一次，確保卡片一定可用。"""
    await async_register_card(hass)

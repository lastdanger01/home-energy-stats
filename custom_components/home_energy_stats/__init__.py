"""Home Energy Stats — 全屋用電量每日統計整合。

從 Home Assistant 的 recorder 長期統計取資料，
提供「每日用電統計表」與對應的 Lovelace 卡片。

資料模型：
  - 使用者指定一個「總用電量」實體（state_class: total_increasing）
  - 整合以該實體的 recorder `change`（每小時增量）算出每日用量
  - 另可指定一個「即時功率」實體，用來算尖峰與平均功率

為什麼不直接用 device_class: energy 的 sum：
  HA 的 `sum` 是「該小時內所有取樣點的累計值之和」，
  對 total_increasing 計數器來說會嚴重高估（累加的是累計器讀數）。
  正確做法是用 `change`（相鄰取樣點的差值總和），這也是 Energy Dashboard 的做法。
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .card import async_register_card
from .const import (
    CONF_ENERGY_ENTITY,
    CONF_POWER_ENTITY,
    DOMAIN,
    STATISTIC_TYPES,
)

# 要轉發的平台。**沒有這行，sensor platform 永遠不會被載入**，
# 整合會顯示 loaded 但一個實體都沒有。
PLATFORMS: list[str] = ["sensor"]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_ENERGY_ENTITY): cv.string,
                vol.Optional(CONF_POWER_ENTITY): cv.string,
            },
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_ENERGY_ENTITY): cv.string,
        vol.Optional(CONF_POWER_ENTITY): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """YAML 設定流程。整合本身不需要 YAML 設定也能工作。"""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config entry 流程（UI 安裝走這條）。"""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_ENERGY_ENTITY: entry.data.get(CONF_ENERGY_ENTITY),
        CONF_POWER_ENTITY: entry.data.get(CONF_POWER_ENTITY),
    }
    _register_services(hass)
    await async_register_card(hass)
    # 一定要轉發，否則 sensor 實體不會建立
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """移除 config entry。"""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    """註冊服務（只註冊一次）。"""
    if hass.services.has_service(DOMAIN, "get_stats"):
        return

    async def _get_stats(call: ServiceCall) -> None:
        """把統計結果寫回 hass.data，讓卡片端與其他自動化取用。"""
        energy = call.data.get(CONF_ENERGY_ENTITY)
        power = call.data.get(CONF_POWER_ENTITY)
        days = int(call.data.get("days", 30))
        result = await async_build_stats(hass, energy, power, days)
        hass.data.setdefault(DOMAIN, {})["last_stats"] = result

    hass.services.async_register(
        DOMAIN,
        "get_stats",
        _get_stats,
        schema=vol.Schema(
            {
                vol.Optional(CONF_ENERGY_ENTITY): cv.string,
                vol.Optional(CONF_POWER_ENTITY): cv.string,
                vol.Optional("days", default=30): cv.positive_int,
            }
        ),
    )

    async def _reload_card(call: ServiceCall) -> None:
        """重新註冊 Lovelace 卡片資源。

        給使用者一個不必改設定檔的修補管道。
        """
        await async_register_card(hass)

    hass.services.async_register(DOMAIN, "reload_card", _reload_card)


async def async_build_stats(
    hass: HomeAssistant,
    energy_entity: str | None,
    power_entity: str | None,
    days: int,
) -> dict[str, Any]:
    """從 recorder 長期統計算出每日用電統計。

    回傳：
      {
        "days": [ {"date": "2026-11-14", "kwh": 21.9, "peak_w": 4353,
                   "mean_w": 412.0, "hours": 24, "source": "change"} ],
        "total_kwh": ..., "avg_kwh": ..., "peak_w": ...,
        "energy_entity": ..., "power_entity": ...,
      }
    """
    from homeassistant.components.recorder import get_instance, history
    from homeassistant.components.recorder.statistics import (
        list_statistic_ids,
        statistics_during_period,
    )
    from homeassistant.util import dt as dt_util

    if not energy_entity:
        return {"days": [], "error": "尚未設定總用電量實體"}

    try:
        # 確認這顆實體真的有被 recorder 記錄
        known = {s["statistic_id"] for s in list_statistic_ids(hass)}
    except Exception as err:  # noqa: BLE001
        # recorder 還沒就緒時不應該讓整合載入失敗
        _LOGGER.debug("recorder 尚未就緒：%s", err)
        return {"days": [], "error": "recorder 尚未就緒，稍後會自動重試"}

    if energy_entity not in known:
        return {
            "days": [],
            "error": (
                f"{energy_entity} 沒有長期統計。"
                "請確認實體存在、且有 state_class: total_increasing。"
            ),
        }

    end = dt_util.now()
    start = end - dt.timedelta(days=days)

    stat_ids = {energy_entity}
    if power_entity:
        stat_ids.add(power_entity)

    rows = statistics_during_period(
        hass,
        start,
        end,
        statistic_ids=stat_ids,
        period="hour",
        units=None,
        types=STATISTIC_TYPES,
    )
    energy_rows = rows.get(energy_entity, [])
    power_rows = rows.get(power_entity, []) if power_entity else []

    # 每小時一格
    buckets: dict[str, dict[str, float]] = {}
    for row in energy_rows:
        when = dt_util.as_utc(row["start"])
        day = when.astimezone(dt_util.DEFAULT_TIME_ZONE).strftime("%Y-%m-%d")
        slot = buckets.setdefault(
            day, {"kwh": 0.0, "peak_w": 0.0, "mean_w_sum": 0.0, "hours": 0}
        )
        # change = 該小時內累計器的總增量，這是正確的用電量
        change = row.get("change")
        if change is not None:
            slot["kwh"] += float(change)
        slot["hours"] += 1

    for row in power_rows:
        when = dt_util.as_utc(row["start"])
        day = when.astimezone(dt_util.DEFAULT_TIME_ZONE).strftime("%Y-%m-%d")
        slot = buckets.get(day)
        if slot is None:
            continue
        if row.get("max") is not None:
            slot["peak_w"] = max(slot["peak_w"], float(row["max"]))
        if row.get("mean") is not None:
            slot["mean_w_sum"] += float(row["mean"])

    days_out = []
    for day in sorted(buckets):
        slot = buckets[day]
        hours = slot["hours"]
        days_out.append(
            {
                "date": day,
                "kwh": round(slot["kwh"], 3),
                "peak_w": round(slot["peak_w"]),
                "mean_w": round(slot["mean_w_sum"] / hours) if hours else 0,
                "hours": hours,
            }
        )

    total = sum(d["kwh"] for d in days_out)
    return {
        "days": days_out,
        "total_kwh": round(total, 3),
        "avg_kwh": round(total / len(days_out), 3) if days_out else 0,
        "peak_w": max((d["peak_w"] for d in days_out), default=0),
        "energy_entity": energy_entity,
        "power_entity": power_entity,
        "generated_at": dt_util.now().isoformat(),
    }

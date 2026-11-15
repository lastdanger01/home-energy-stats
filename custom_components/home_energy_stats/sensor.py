"""Home Energy Stats 的 sensor 平台。

提供幾個衍生實體：
  sensor.energy_stats_today      今日用電量 (kWh)
  sensor.energy_stats_7d         近 7 天用電量 (kWh)
  sensor.energy_stats_30d        近 30 天用電量 (kWh)
  sensor.energy_stats_peak       尖峰功率 (W)
  sensor.energy_stats_daily      每日明細表（attributes 帶完整表格）

`sensor.energy_stats_daily` 的 attributes 會帶：
  days: [{"date": "2026-11-14", "kwh": 21.9, "peak_w": 4353, "mean_w": 412}, ...]
卡片就是讀這個實體的 attributes 畫表格。
"""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import async_build_stats
from .const import CONF_ENERGY_ENTITY, CONF_POWER_ENTITY, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)
STATS_DAYS = 30


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """建立 sensor 實體。"""
    energy_entity = entry.data.get(CONF_ENERGY_ENTITY)
    power_entity = entry.data.get(CONF_POWER_ENTITY)
    if not energy_entity:
        _LOGGER.error("沒有設定總用電量實體，無法建立統計")
        return

    async def _async_update_data() -> dict:
        return await async_build_stats(
            hass, energy_entity, power_entity, STATS_DAYS
        )

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN} stats",
        update_method=_async_update_data,
        update_interval=SCAN_INTERVAL,
    )
    await coordinator.async_config_entry_first_refresh()

    async_add_entities(
        [
            EnergyStatsSensor(coordinator, "today", "今日用電量", UnitOfEnergy.KILO_WATT_HOUR),
            EnergyStatsSensor(coordinator, "7d", "近 7 天用電量", UnitOfEnergy.KILO_WATT_HOUR),
            EnergyStatsSensor(coordinator, "30d", "近 30 天用電量", UnitOfEnergy.KILO_WATT_HOUR),
            EnergyStatsSensor(coordinator, "peak", "尖峰功率", UnitOfPower.WATT),
            EnergyStatsDailyTable(coordinator),
        ]
    )


class EnergyStatsSensor(CoordinatorEntity, SensorEntity):
    """單一數值的統計感測器。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator, key: str, name: str, unit: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_unique_id = f"{DOMAIN}_{key}"

        if key == "peak":
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:
            # **不能用 device_class: energy**。
            # energy device class 只允許 total / total_increasing，
            # 搭配 measurement 會被 HA 記警告：
            # "state class 'measurement' which is impossible
            #  considering device class ('energy')"。
            # 這些是「區間用量」的滾動值，不是單調遞增的計數器，
            # 所以不設 device_class，只留 unit。
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        days = data.get("days") or []
        if not days:
            return None
        if self._key == "peak":
            return data.get("peak_w")
        if self._key == "today":
            return days[-1]["kwh"]
        n = 7 if self._key == "7d" else STATS_DAYS
        recent = days[-n:]
        return round(sum(d["kwh"] for d in recent), 3)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "days_count": len(data.get("days") or []),
            "energy_entity": data.get("energy_entity"),
            "power_entity": data.get("power_entity"),
        }


class EnergyStatsDailyTable(CoordinatorEntity, SensorEntity):
    """每日明細表（把完整表格放在 attributes）。"""

    _attr_has_entity_name = True
    _attr_name = "每日用電明細"
    _attr_icon = "mdi:table"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_daily_table"

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return data.get("total_kwh")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "days": data.get("days") or [],
            "total_kwh": data.get("total_kwh"),
            "avg_kwh": data.get("avg_kwh"),
            "peak_w": data.get("peak_w"),
            "energy_entity": data.get("energy_entity"),
            "power_entity": data.get("power_entity"),
            "generated_at": data.get("generated_at"),
        }

"""Home Energy Stats 的 config flow。

使用者要指定：
  - 總用電量實體（state_class: total_increasing，通常是 ch1+ch2 的模板感測器）
  - （選填）即時功率實體，用來算尖峰與平均功率

流程刻意簡單：只選實體，不填網址、不填任何環境專屬資訊。
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import CONF_ENERGY_ENTITY, CONF_POWER_ENTITY, DOMAIN


def _energy_selector() -> Any:
    """挑選能源實體。

    只顯示 energy device_class 的實體，避免選到不對的感測器。
    """
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=[
                {"domain": "sensor", "device_class": "energy"},
                {"domain": "sensor", "device_class": "monetary"},
            ]
        )
    )


def _power_selector() -> Any:
    """挑選功率實體。"""
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            filter=[{"domain": "sensor", "device_class": "power"}]
        )
    )


class HomeEnergyStatsFlow(ConfigFlow, domain=DOMAIN):
    """處理 Home Energy Stats 的 config flow。"""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """使用者選擇實體。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            energy = user_input.get(CONF_ENERGY_ENTITY)
            power = user_input.get(CONF_POWER_ENTITY)

            if not energy:
                errors[CONF_ENERGY_ENTITY] = "必須指定總用電量實體"
            else:
                # 同一組實體不重複建立
                await self.async_set_unique_id(f"{energy}|{power or ''}")
                self._abort_if_unique_id_configured()
                title = self._title_for(energy)
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_ENERGY_ENTITY: energy,
                        CONF_POWER_ENTITY: power,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ENERGY_ENTITY): _energy_selector(),
                    vol.Optional(CONF_POWER_ENTITY): _power_selector(),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def _title_for(entity_id: str) -> str:
        """從實體名稱產生標題。"""
        friendly = entity_id.split(".")[-1].replace("_", " ").title()
        return f"Energy Stats · {friendly}"

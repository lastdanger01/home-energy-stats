"""Home Energy Stats 常數。"""

from typing import Final

DOMAIN: Final = "home_energy_stats"

CONF_ENERGY_ENTITY: Final = "energy_entity"
CONF_POWER_ENTITY: Final = "power_entity"

# statistics_during_period 要的統計欄位
STATISTIC_TYPES: Final = {"change", "max", "mean", "min", "state"}

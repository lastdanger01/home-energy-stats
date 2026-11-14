# Home Energy Stats

全屋用電量每日統計的 Home Assistant 自訂整合。

把 Home Assistant recorder 的長期統計整理成一張**每日用電統計表**，用 Lovelace 卡片直接顯示。

## 特色

- **數字正確**：用 recorder 的 `change`（累計器每小時增量）算用量，
  而不是 `sum`。對 `total_increasing` 計數器來說 `sum` 會把累計讀數重複累加、
  嚴重高估——這也是 Energy Dashboard 自己的做法。
- **零設定**：不需要填網址、不需要 YAML 區塊，只要在 UI 選一個實體。
- **不需要重啟**：卡片資源即時生效。
- **支援多迴路**：你的「總用電量」可以是 ch1 + ch2 的 template sensor，
  整合直接讀它。

## 安裝

### HACS

1. HACS → 設定 → 自訂存放庫 → 加上 `lastdanger01/home-energy-stats`
2. HACS → 整合 → 搜尋 **Home Energy Stats** → 下載
3. **重啟 Home Assistant**
4. 設定 → 裝置與服務 → 整合 → 新增整合 → 搜尋 **Home Energy Stats**
5. 選擇你的「總用電量」實體（選填「即時功率」實體）

> 如果你之前手動上傳過 `custom_components/home_energy_stats`，
> 請先刪掉那份再重啟，否則會和 HACS 的版本衝突。

### 手動

把 `custom_components/home_energy_stats` 整個資料夾複製到 HA 的
`config/custom_components/` 底下，然後重啟 HA。

## 設定

| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| 總用電量實體 | 是 | `device_class: energy` + `state_class: total_increasing` |
| 即時功率實體 | 否 | `device_class: power`，用來算尖峰與平均功率 |

總用電量實體如果是多迴路相加，先在 HA 裡用 template sensor 做好：

```yaml
template:
  - sensor:
      - name: "總用電量"
        unique_id: total_home_energy
        unit_of_measurement: kWh
        device_class: energy
        state_class: total_increasing
        state: >
          {% set a = states('sensor.ch1_energy') %}
          {% set b = states('sensor.ch2_energy') %}
          {% if a in ['unknown', 'unavailable', 'none']
                or b in ['unknown', 'unavailable', 'none'] %}
            {{ none }}
          {% else %}
            {{ (a | float(0) + b | float(0)) | round(3) }}
          {% endif %}
```

## 產生的實體

| 實體 | 說明 |
| --- | --- |
| `sensor.<你的實體>_today` | 今日用電量（kWh） |
| `sensor.<你的實體>_7d` | 近 7 天用電量（kWh） |
| `sensor.<你的實體>_30d` | 近 30 天用電量（kWh） |
| `sensor.<你的實體>_peak` | 尖峰功率（W） |
| `sensor.<你的實體>_daily_table` | 每日明細（完整表格在 attributes） |

實際 entity_id 會依你的設定命名為 `sensor.home_energy_stats_today` 之類。

## Lovelace 卡片

加入卡片後選「Home Energy Stats」：

```yaml
type: custom:home-energy-stats-card
entity: sensor.home_energy_stats_daily_table
days: 14
title: 每日用電統計
```

卡片顯示區間總量、日均、尖峰，以及每天的用量長條圖與尖峰功率。

## 服務

| 服務 | 用途 |
| --- | --- |
| `home_energy_stats.get_stats` | 取得統計（可指定實體與天數） |
| `home_energy_stats.reload_card` | 重新註冊卡片資源，不必重啟 HA |

## 已知限制

- **只統計 recorder 有記錄到的期間**。整合剛裝好時，短期內資料會少。
- 感測器若中途停止更新，恢復時會把累積量一次補記，
  該日數字會偏高但**總量正確**。這個整合不做補記校正，
  需要校正請看你的原始紀錄工具。
- 每日統計以 HA 的時區（`DEFAULT_TIME_ZONE`）切日。

## 授權

MIT

/* Home Energy Stats Lovelace 卡片
 *
 * 讀 sensor.<...>_daily_table 的 attributes.days 畫出每日用電統計表。
 *
 * 註冊方式有兩條通道（都要做，否則 YAML mode / storage mode 會有一邊失效）：
 *   1. Lovelace resource（res_type: module）
 *   2. frontend extra_module_url
 */

const DOMAIN = "home-energy-stats";

class HomeEnergyStatsCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("home-energy-stats-card-editor");
  }

  static getStubConfig() {
    return { entity: "", days: 14, show_header: true };
  }

  setConfig(config) {
    if (!config) {
      throw new Error("請設定卡片");
    }
    this._config = {
      entity: config.entity || "",
      days: config.days ?? 14,
      show_header: config.show_header !== false,
      title: config.title || "每日用電統計",
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config) this._render();
  }

  getCardSize() {
    const rows = this._rows().length;
    return Math.ceil((rows + 3) / 3);
  }

  _entityId() {
    return this._config.entity;
  }

  _state() {
    if (!this._hass || !this._entityId()) return null;
    return this._hass.states[this._entityId()];
  }

  _rows() {
    const state = this._state();
    if (!state) return [];
    const days = state.attributes?.days || [];
    const n = Number(this._config.days) || 14;
    return days.slice(-n).reverse();
  }

  _render() {
    if (!this.isConnected) return;
    const rows = this._rows();
    const state = this._state();
    const attrs = state?.attributes || {};

    if (!this._entityId() || !state) {
      this.innerHTML = `
        <div class="card">
          <div class="content">${DOMAIN}</div>
          <div class="secondary">尚未設定實體，請在卡片編輯畫面選擇「每日用電明細」實體。</div>
        </div>`;
      return;
    }

    const total = attrs.total_kwh ?? 0;
    const avg = attrs.avg_kwh ?? 0;
    const peak = attrs.peak_w ?? 0;
    const maxKwh = Math.max(...rows.map((r) => r.kwh || 0), 1);

    const body = rows.length
      ? rows
          .map((r) => {
            const pct = Math.max(2, Math.round(((r.kwh || 0) / maxKwh) * 100));
            return `
              <div class="row">
                <div class="date">${r.date}</div>
                <div class="bar-wrap"><div class="bar" style="width:${pct}%"></div></div>
                <div class="kwh">${(r.kwh ?? 0).toFixed(2)}</div>
                <div class="peak">${r.peak_w ?? 0} W</div>
              </div>`;
          })
          .join("")
      : '<div class="secondary">尚無統計資料（recorder 可能還沒記錄到）</div>';

    this.innerHTML = `
      <ha-card header="${this._config.title}">
        <div class="stats">
          <div class="stat">
            <div class="stat-value">${Number(total).toFixed(1)}</div>
            <div class="stat-label">區間總量 kWh</div>
          </div>
          <div class="stat">
            <div class="stat-value">${Number(avg).toFixed(1)}</div>
            <div class="stat-label">日均 kWh</div>
          </div>
          <div class="stat">
            <div class="stat-value">${peak}</div>
            <div class="stat-label">尖峰 W</div>
          </div>
        </div>
        <div class="table">
          <div class="row head">
            <div class="date">日期</div>
            <div class="bar-wrap"></div>
            <div class="kwh">kWh</div>
            <div class="peak">尖峰</div>
          </div>
          ${body}
        </div>
      </ha-card>
      <style>
        ha-card { padding: 12px 16px 16px; }
        .stats { display: flex; gap: 8px; margin-bottom: 12px; }
        .stat { flex: 1; text-align: center; padding: 8px 4px;
                background: var(--card-background-color, rgba(127,127,127,.1));
                border-radius: 8px; }
        .stat-value { font-size: 22px; font-weight: 600; }
        .stat-label { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
        .table { font-size: 13px; }
        .row { display: grid; grid-template-columns: 78px 1fr 62px 64px;
               align-items: center; gap: 6px; padding: 3px 0; }
        .row.head { color: var(--secondary-text-color); font-size: 11px;
                    border-bottom: 1px solid var(--divider-color, rgba(127,127,127,.25));
                    padding-bottom: 6px; margin-bottom: 4px; }
        .bar-wrap { height: 12px; background: rgba(127,127,127,.14); border-radius: 6px; overflow: hidden; }
        .bar { height: 100%; background: var(--energy-grid-consumption-color, #4caf50);
               border-radius: 6px; }
        .kwh, .peak { text-align: right; font-variant-numeric: tabular-nums; }
        .date { color: var(--secondary-text-color); }
        .secondary { color: var(--secondary-text-color); padding: 8px 0; }
      </style>`;
  }
}

class HomeEnergyStatsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { entity: "", days: 14, show_header: true, ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this.isConnected) return;
    const options = Object.keys(this._hass?.states || {})
      .filter((id) => id.startsWith("sensor.") && id.includes("energy"))
      .map((id) => `<option value="${id}">${id}</option>`)
      .join("");
    this.innerHTML = `
      <div class="editor">
        <label>實體</label>
        <select class="entity">
          <option value="">請選擇</option>
          ${options}
        </select>
        <label>顯示天數</label>
        <input class="days" type="number" min="1" max="90" value="${this._config.days ?? 14}">
        <label>標題</label>
        <input class="title" type="text" value="${this._config.title || "每日用電統計"}">
      </div>
      <style>
        .editor { display: flex; flex-direction: column; gap: 6px; }
        label { font-size: 12px; color: var(--secondary-text-color); }
      </style>`;

    this.querySelector(".entity").value = this._config.entity || "";
    this.querySelector(".entity").addEventListener("change", (e) => {
      this._config.entity = e.target.value;
      this._fireChange();
    });
    this.querySelector(".days").addEventListener("change", (e) => {
      this._config.days = Number(e.target.value);
      this._fireChange();
    });
    this.querySelector(".title").addEventListener("change", (e) => {
      this._config.title = e.target.value;
      this._fireChange();
    });
  }

  _fireChange() {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }
}

if (!customElements.get("home-energy-stats-card")) {
  customElements.define("home-energy-stats-card", HomeEnergyStatsCard);
}
if (!customElements.get("home-energy-stats-card-editor")) {
  customElements.define("home-energy-stats-card-editor", HomeEnergyStatsCardEditor);
}

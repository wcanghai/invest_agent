(() => {
  "use strict";

  const CHANGE_HEADERS = new Set(["涨跌幅", "24h 变动"]);
  const PERCENTILE_HEADER = "三年价格分位";

  function numericValue(cell) {
    if (!cell) return Number.NaN;
    const match = cell.textContent.replaceAll(",", "").match(/[+-]?\d+(?:\.\d+)?/);
    return match ? Number.parseFloat(match[0]) : Number.NaN;
  }

  function markSignal(cell, kind, label) {
    cell.classList.add(`signal-${kind}`);
    const marker = document.createElement("span");
    marker.className = "signal-marker";
    marker.textContent = label;
    marker.setAttribute("aria-hidden", "true");
    cell.append(marker);
    cell.title = label;
  }

  function highlightRows(table, changeIndex, percentileIndex) {
    Array.from(table.tBodies[0]?.rows ?? []).forEach((row) => {
      const change = numericValue(row.cells[changeIndex]);
      if (change > 3) markSignal(row.cells[changeIndex], "up", "强势");
      if (change < -3) markSignal(row.cells[changeIndex], "down", "弱势");

      if (percentileIndex < 0) return;
      const percentile = numericValue(row.cells[percentileIndex]);
      if (percentile > 80) markSignal(row.cells[percentileIndex], "high", "高位");
      if (percentile < 20) markSignal(row.cells[percentileIndex], "low", "低位");
    });
  }

  function sortRows(tbody, defaultRows, changeIndex, direction) {
    if (direction === "default") {
      defaultRows.forEach((row) => tbody.append(row));
      return;
    }

    const multiplier = direction === "descending" ? -1 : 1;
    const sortedRows = [...defaultRows].sort((left, right) => {
      const leftValue = numericValue(left.cells[changeIndex]);
      const rightValue = numericValue(right.cells[changeIndex]);
      if (Number.isNaN(leftValue)) return Number.isNaN(rightValue) ? 0 : 1;
      if (Number.isNaN(rightValue)) return -1;
      return (leftValue - rightValue) * multiplier;
    });
    sortedRows.forEach((row) => tbody.append(row));
  }

  function addSortControls(table, changeIndex) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const defaultRows = Array.from(tbody.rows);
    const controls = document.createElement("div");
    controls.className = "table-sort-controls";
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", "按照涨跌幅排序");

    const choices = [
      ["default", "默认排序"],
      ["descending", "涨幅优先"],
      ["ascending", "跌幅优先"],
    ];
    choices.forEach(([direction, label], index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.dataset.sortDirection = direction;
      button.setAttribute("aria-pressed", index === 0 ? "true" : "false");
      button.addEventListener("click", () => {
        sortRows(tbody, defaultRows, changeIndex, direction);
        controls.querySelectorAll("button").forEach((item) => {
          item.setAttribute("aria-pressed", String(item === button));
        });
      });
      controls.append(button);
    });
    table.before(controls);
  }

  function enhanceTable(table) {
    const headers = Array.from(table.tHead?.rows[0]?.cells ?? []).map((cell) =>
      cell.textContent.trim()
    );
    const changeIndex = headers.findIndex((header) => CHANGE_HEADERS.has(header));
    if (changeIndex < 0) return;
    const percentileIndex = headers.indexOf(PERCENTILE_HEADER);
    highlightRows(table, changeIndex, percentileIndex);
    addSortControls(table, changeIndex);
  }

  document.querySelectorAll("[data-enhanced-report] table").forEach(enhanceTable);
})();

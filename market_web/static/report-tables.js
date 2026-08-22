(() => {
  "use strict";

  const CHANGE_HEADERS = new Set(["涨跌幅", "24h 变动"]);
  const PERCENTILE_HEADER = "三年价格分位";
  const SORT_STATES = [
    { direction: "default", label: "配置顺序" },
    { direction: "descending", label: "涨幅优先" },
    { direction: "ascending", label: "跌幅优先" },
  ];

  function numericValue(cell) {
    if (!cell) return Number.NaN;
    const match = cell.textContent.replaceAll(",", "").match(/[+-]?\d+(?:\.\d+)?/);
    return match ? Number.parseFloat(match[0]) : Number.NaN;
  }

  function markSignal(cell, kind) {
    cell.classList.add(`signal-${kind}`);
  }

  function highlightRows(table, changeIndex, percentileIndex) {
    Array.from(table.tBodies[0]?.rows ?? []).forEach((row) => {
      const change = numericValue(row.cells[changeIndex]);
      if (change > 3) markSignal(row.cells[changeIndex], "up");
      if (change < -3) markSignal(row.cells[changeIndex], "down");

      if (percentileIndex < 0) return;
      const percentile = numericValue(row.cells[percentileIndex]);
      if (percentile > 80) markSignal(row.cells[percentileIndex], "high");
      if (percentile < 20) markSignal(row.cells[percentileIndex], "low");
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

  function addSortControl(table, header, changeIndex) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const defaultRows = Array.from(tbody.rows);
    const button = document.createElement("button");
    let stateIndex = 0;

    function showState() {
      const state = SORT_STATES[stateIndex];
      const nextState = SORT_STATES[(stateIndex + 1) % SORT_STATES.length];
      button.dataset.sortDirection = state.direction;
      button.setAttribute(
        "aria-label",
        `当前${state.label}，点击切换为${nextState.label}`
      );
      button.title = `当前：${state.label}`;
      header.setAttribute(
        "aria-sort",
        state.direction === "default" ? "none" : state.direction
      );
    }

    header.classList.add("sortable-column");
    button.type = "button";
    button.className = "sort-toggle";
    button.addEventListener("click", () => {
      stateIndex = (stateIndex + 1) % SORT_STATES.length;
      const state = SORT_STATES[stateIndex];
      sortRows(tbody, defaultRows, changeIndex, state.direction);
      showState();
    });
    showState();
    header.append(button);
  }

  function enhanceTable(table) {
    const headers = Array.from(table.tHead?.rows[0]?.cells ?? []).map((cell) =>
      cell.textContent.trim()
    );
    const changeIndex = headers.findIndex((header) => CHANGE_HEADERS.has(header));
    if (changeIndex < 0) return;
    const percentileIndex = headers.indexOf(PERCENTILE_HEADER);
    highlightRows(table, changeIndex, percentileIndex);
    addSortControl(table, table.tHead.rows[0].cells[changeIndex], changeIndex);
  }

  document.querySelectorAll("[data-enhanced-report] table").forEach(enhanceTable);
})();

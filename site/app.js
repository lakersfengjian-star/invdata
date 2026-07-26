const tabs = Array.from(document.querySelectorAll(".category-tab"));
const panels = Array.from(document.querySelectorAll(".category-panel"));
const refreshButton = document.querySelector("#refresh-data");
const refreshStatus = document.querySelector("#refresh-status");

function activateCategory(target) {
  tabs.forEach((tab) => {
    const active = tab.dataset.target === target;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  panels.forEach((panel) => {
    const active = panel.dataset.category === target;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => activateCategory(tab.dataset.target));
});

if (refreshButton && refreshStatus) {
  function expectedLatestTradingDay() {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    while (d.getDay() === 0 || d.getDay() === 6) {
      d.setDate(d.getDate() - 1);
    }
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    refreshStatus.textContent = "正在检查数据是否已是最新...";
    try {
      const metaResponse = await fetch(`meta.json?t=${Date.now()}`, { cache: "no-store" });
      if (metaResponse.ok) {
        const meta = await metaResponse.json();
        const latestDaily = meta.latest_daily_date || meta.latest_common_date || "";
        const expected = expectedLatestTradingDay();
        if (latestDaily && latestDaily >= expected) {
          refreshStatus.textContent = `数据已更新（截至 ${latestDaily}），请勿重复获取，避免消耗 API 与 token 额度。`;
          refreshButton.disabled = false;
          return;
        }
      }
    } catch (error) {
      // meta 不可用时继续按原流程刷新。
    }
    refreshStatus.textContent = "正在提交刷新任务...";
    try {
      const response = await fetch("/api/refresh", { method: "POST" });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(result.message || "刷新任务提交失败");
      }
      refreshStatus.textContent = "刷新任务已提交，数据更新和部署通常需要几分钟。";
    } catch (error) {
      refreshStatus.textContent = error.message || "刷新任务提交失败";
    } finally {
      refreshButton.disabled = false;
    }
  });
}

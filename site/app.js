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
  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
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

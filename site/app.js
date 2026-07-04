const tabs = Array.from(document.querySelectorAll(".category-tab"));
const panels = Array.from(document.querySelectorAll(".category-panel"));

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

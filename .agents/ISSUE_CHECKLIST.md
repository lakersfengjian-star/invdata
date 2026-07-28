# 投研数据页问题核查清单

用途：网站维护或交接时，先按本文定位常见问题，避免反复读取长对话和大文件。

## 1. 网站看起来没有自动更新

优先检查三件事：

1. `site/meta.json`：查看 `build_time`、`latest_daily_date`、`charts` 各图表日期。
2. 根目录 `index.html` 与 `site/index.html`：两者必须由 `scripts/build_site_from_processed.py` 同步生成。
3. GitHub Actions 自动提交范围：`.github/workflows/auto-update-dashboard.yml` 必须包含 `git add index.html data/processed data/raw output/charts site`。

历史根因：Vercel 根路径会优先读取根目录 `index.html`。如果自动任务只提交 `site/index.html`，线上 `/` 仍可能显示旧根首页，即使 `site/` 已更新。

## 2. 自动任务是否真的运行

检查：

```bash
git log --oneline -5
cat data/processed/update_audit.json
```

期望：

- `update_audit.json` 中有最近一次实际运行脚本的 `checked_at`、`expected_latest_daily`、`ran`、`skipped`、`build`。
- 全部数据已新鲜时，调度器可能只打印 no-op 摘要，不产生新提交。
- GitHub Actions 使用 `scripts/run_scheduled_updates.py --mode scheduled`，北京时间每天 06:00 运行。

## 3. 日期显示异常

页面头部不再使用单一 `latest_common_date` 代表全站，而是分开显示：

- 页面构建：本次建站时间。
- 日频截至：日频图表的最大最新日期。
- 周频截至：中信拥挤度、PB-ROE 等周频图表最新日期。
- 月/季频截至：宏观、工业企业利润等月频/季频图表最新日期。

若某张图滞后，优先看 `site/meta.json` 的 `charts` 字段，不要只看网页头部。

## 4. 图片不显示或显示旧图

检查：

```bash
rg -n "assets/charts|../output/charts" index.html site/index.html
find site/assets/charts -maxdepth 1 -type f -name '*.png' -print | sort
```

期望：

- 页面路径为 `assets/charts/xxx.png?v=<构建时间版本号>`。
- 不应出现 `../output/charts`。
- `site/assets/charts/` 至少包含当前所有 PNG。

若图片旧但路径正确，重新运行：

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache MPLCONFIGDIR=/tmp/matplotlib-cache /Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build_site_from_processed.py
```

## 5. 中文乱码或字体异常

检查：

- HTML 必须包含 `<meta charset="utf-8">`。
- Python 写 HTML/JSON 必须使用 `encoding="utf-8"`。
- GitHub Actions 安装 `fonts-noto-cjk`。
- Matplotlib 字体优先级包含 `Noto Sans CJK SC`、`Microsoft YaHei`、`SimHei`、`PingFang SC`。

## 6. 刷新按钮失败

检查：

- Vercel 环境变量 `GITHUB_PAT` 是否存在。
- `/api/refresh` 是否返回 202。
- GitHub token 是否有仓库 Actions workflow dispatch 权限。
- 手动点击后，GitHub Actions 是否出现 `workflow_dispatch` 运行。

刷新按钮只负责触发后台任务，不直接在 Vercel 上抓数据。数据更新后还需要 GitHub Actions 提交，Vercel 再自动部署。

## 7. Wind 相关数据滞后

GitHub Actions 没有本地 Wind 授权。以下数据需要本地任务或手动刷新后提交：

- 上证等权情绪指数中的 Wind 依赖项。
- 中信一级行业拥挤度。
- 中信一级行业 PB-ROE。

若线上这些图滞后，先检查本地 Wind 任务和 `data/raw/citic_industry_crowding_weekly.csv`，不要在 GitHub Actions 上排障 Wind。

## 8. 文件清理原则

可删除：

- 根目录或 `scripts/` 下明显临时的 `test_*.py`、`check_*.py`、`fix_build*.py`。
- 已被正式脚本替代的手工诊断文件。

不要轻易删除：

- `data/raw/` 中手工导入或 Wind 导出的原始数据。
- `data/processed/` 中时间序列底座。
- `output/charts/` 与 `site/assets/charts/` 中当前页面引用的 PNG。
- `site/assets/docs/` 和用户研究资料。

清理后必须运行：

```bash
git status -sb
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m py_compile scripts/build_site_from_processed.py scripts/run_scheduled_updates.py
```

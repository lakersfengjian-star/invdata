# Token 节省与发布优化规范

用途：后续 agent 维护本项目时必须优先遵守本文，避免再次通过对话搬运大文件、完整历史数据或大段脚本，降低 token 消耗并提高发布稳定性。

## 强制原则

1. 禁止通过聊天或 GitHub 连接器逐段上传大体量 base64、CSV、PNG 或完整历史数据，除非没有任何可用替代方案。
2. 优先使用本地文件系统、`apply_patch` 小范围修改、正常 `git push` 或 GitHub 原生提交能力。
3. 时间序列必须本地持久化，后续只补充最新交易日和缺口日期。
4. GitHub Pages 默认使用离线构建：读取 `data/processed` 汇总表，生成 `site/`，不在 Actions 中在线抓全量行情。
5. 大文件只在本地缓存；远端只保留必要的小型汇总数据、构建脚本和静态站点。
6. 修改代码时先定位最小文件和最小函数，不读取或重写无关大文件。
7. 发布前后核验使用固定命令和清单，不重复做开放式探索。

## 本次高消耗环节复盘

### 最高消耗：数据快照分片上传

曾通过 GitHub 连接器逐个上传 `processed_snapshot.py.part01` 至 `part05`。每个分片约 10KB 文本，需要先读出再作为工具参数完整提交，token 消耗很高。

后续规则：

- 不再把完整快照转成 base64 后通过对话上传。
- 优先配置本机 GitHub 凭证后执行正常 `git push`。
- 若必须使用连接器，只提交小补丁或小文件，不提交大段历史数据。

### 次高消耗：完整脚本读写

曾完整读取并更新 `scripts/build_site_from_processed.py`。几千 token 的脚本读写可接受一次，但不应成为常规流程。

后续规则：

- 将字体配置、页面模板、图表函数逐步拆成小模块。
- 修改字体、路径、标题等问题时，只 patch 相关函数。
- 使用 `rg -n` 精准定位，再用 `sed -n` 小范围读取。

### 中等消耗：线上状态反复轮询

Actions 状态、页面 HTML 和图片链接检查单次不大，但多次轮询会累积。

后续规则：

- 发布后最多按固定间隔检查 2-3 次。
- 若 Actions 仍在运行，报告“等待 Pages 完成”，不要长时间反复轮询。
- 验收只检查首页、图片路径和代表性 PNG，必要时再抽查全部图片。

## 标准低 token 工作流

### 1. 先读项目文档

每次维护先读：

- `.agents/README.md`
- `.agents/INVEST_DASHBOARD_STANDARD.md`
- `.agents/ISSUE_CHECKLIST.md`
- `.agents/TOKEN_EFFICIENT_WORKFLOW.md`

### 2. 本地增量更新数据

优先读取 `data/processed/metadata.json` 和各 CSV 最大日期。

只抓取：

- 本地最大日期之后的新交易日
- 历史缺口日期
- 用户明确要求重算的单个指标或图表

不要默认全量回溯。

### 3. 使用离线构建生成网页

默认运行：

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache MPLCONFIGDIR=/tmp/matplotlib-cache /Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build_site_from_processed.py
```

该步骤只依赖 `data/processed` 汇总文件，生成：

- `output/charts/*.png`
- `site/index.html`
- `site/assets/charts/*.png`

### 4. 本地最小核验

固定检查：

```bash
rg -n "assets/charts|截至|区间|图三|图四" site/index.html
find site/assets/charts -maxdepth 1 -type f -print | sort
```

如涉及中文显示，额外查看一张本地图：

```text
site/assets/charts/fig_001_broad_etf_flow.png
```

### 5. 发布优先级

首选：

```bash
git status --short
git add <必要文件>
git commit -m "<清晰说明>"
git push
```

如果本机 GitHub 凭证不可用：

- 只用 GitHub 连接器更新小文件。
- 不通过连接器上传大型 base64 分片。
- 若必须远端更新大文件，先向用户说明 token 成本和替代方案。

### 6. 线上最小核验

固定检查：

```bash
curl -L -sS -o /tmp/invdata-page.html -w '%{http_code} %{url_effective}\n' https://lakersfengjian-star.github.io/invdata/
rg -n "assets/charts|截至|区间" /tmp/invdata-page.html
curl -L -sS -o /tmp/chart.png -w '%{http_code} %{size_download}\n' https://lakersfengjian-star.github.io/invdata/assets/charts/fig_001_broad_etf_flow.png
```

期望：

- 首页 HTTP `200`
- 图片 HTTP `200`
- 图片大小明显大于 10KB
- 页面最新日期与 `metadata.json` 一致

## 数据与文件保留策略

### 必须本地保留

- `.work/cache/` 下的接口缓存
- 逐股日成交额明细缓存
- 大型历史明细 CSV
- 手动导入的 Wind/Tushare 原始文件

### 可提交远端

- `scripts/*.py`
- `.github/workflows/pages.yml`
- `.agents/*.md`
- `data/processed` 中必要小型汇总表
- `site/` 静态发布结果
- `output/charts` 高分辨率图表，若仓库体积可接受

### 谨慎提交远端

- 大型逐股明细
- 大型 base64 快照
- 临时诊断文件
- `.work/cache/`

## 后续结构优化方向

1. 把 `scripts/build_site_from_processed.py` 拆为：
   - `scripts/dashboard/fonts.py`
   - `scripts/dashboard/charts.py`
   - `scripts/dashboard/site.py`
   - `scripts/dashboard/config.py`
2. 把 HTML 模板独立为 `site_template.html`，减少改文案时读取整段 Python。
3. 将数据更新脚本按指标拆分，支持指定图表编号更新。
4. 增加 `make build-site`、`make verify-site`、`make publish`，让后续 agent 少记命令。
5. 配置本机 GitHub 凭证，避免使用连接器搬运文件内容。

## 后续执行口径

后续任何 agent 在本项目内执行数据更新、网页修复、GitHub Pages 发布时，应默认采用本文流程。若因权限、网络或凭证问题无法执行，应先说明阻塞点和 token 成本，再选择最小替代路径。

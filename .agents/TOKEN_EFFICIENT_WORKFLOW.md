# Token 节省与发布优化规范

用途：后续 agent 维护本项目时必须优先遵守本文，避免再次通过对话搬运大文件、完整历史数据或大段脚本，降低 token 消耗并提高发布稳定性。

## 2026-07-04 复盘结论

上一轮尝试通过 agent 协助 GitHub 凭证、VS Code UI、GitHub 连接器和终端推送，事实证明并不省 token。高消耗不只来自数据文件，也来自反复读取状态、解释认证失败、操作 UI、处理分叉和冲突。

后续必须采用新的边界：

- agent 负责：本地 Python 抓数、增量补数、生成 CSV/PNG/HTML、最小本地核验、更新文档。
- VS Code 负责：GitHub 登录、凭证保存、分支管理、提交、推送、查看 GitHub Actions。
- 用户负责：在 VS Code/GitHub 浏览器授权一次，或点击 Source Control 中的 Push/Sync。
- 禁止 agent 为推送目的反复操作 VS Code UI、浏览器登录、验证码、GitHub 凭证、SSH key、PAT 或大文件连接器上传。

如果后续需要发布，agent 的交付物应停在“本地文件已生成、提交清单已确认、VS Code 推送步骤已给出”。除非用户明确要求 agent 继续处理 Git，并确认愿意承担额外 token 成本，否则不进入认证和推送排障。

## 强制原则

1. 禁止通过聊天或 GitHub 连接器逐段上传大体量 base64、CSV、PNG 或完整历史数据，除非没有任何可用替代方案。
2. 优先使用本地文件系统、`apply_patch` 小范围修改、Python 本地生成和 VS Code 原生 Git 推送。
3. 时间序列必须本地持久化，后续只补充最新交易日和缺口日期。
4. GitHub Pages 默认使用离线构建：读取 `data/processed` 汇总表，生成 `site/`，不在 Actions 中在线抓全量行情。
5. 大文件只在本地缓存；远端只保留必要的小型汇总数据、构建脚本和静态站点。
6. 修改代码时先定位最小文件和最小函数，不读取或重写无关大文件。
7. 发布前后核验使用固定命令和清单，不重复做开放式探索。
8. GitHub 认证、Token、SSH key、VS Code 登录弹窗均不作为 agent 常规任务；这些由 VS Code/GitHub 桌面登录流程处理。
9. 大型 CSV 只用 `head`、`tail`、`wc -l`、列名和元数据核验，不把全文件内容输出到对话。

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

### 隐性高消耗：凭证与 UI 排障

上一轮 VS Code、SSH、HTTPS、`gh auth`、剪贴板和浏览器授权之间多次切换，消耗大量上下文，但没有直接改善图表质量。

后续规则：

- 不把“推送失败”升级为长时间认证排障。
- 不通过 agent 操作 VS Code UI 来完成 GitHub 登录。
- 不在对话中处理 PAT、密码、验证码或浏览器授权。
- 若本地 Git 推送失败，输出固定 VS Code 操作步骤，由用户在 VS Code 完成推送。
- agent 后续只做轻量验证，例如 `git status -sb` 或线上首页检查。

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

### 5. VS Code 发布边界

agent 可准备提交，但默认不负责认证和推送。推荐流程：

```bash
git status --short
```

然后在 VS Code 中：

1. 打开 Source Control。
2. 检查变更清单。
3. 填写提交信息并 Commit，或确认 agent 已完成本地 commit。
4. 点击 Push/Sync。
5. 通过 VS Code/GitHub 浏览器授权。

若需要命令行辅助，只给固定命令，不持续排障：

```bash
cd /Users/jianfeng/Documents/投研助手
git status -sb
git log --oneline -3
git push origin HEAD:main
```

如果凭证不可用：

- 转交 VS Code 登录处理。
- 不再通过 GitHub 连接器上传 PNG/CSV。
- 不再尝试在 agent 会话内配置 PAT、Keychain、SSH 或 OAuth。

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
5. 将发布职责明确迁移到 VS Code Source Control，agent 只准备本地结果和提交清单。

## 后续执行口径

后续任何 agent 在本项目内执行数据更新、网页修复、GitHub Pages 发布时，应默认采用本文流程。若因权限、网络或凭证问题无法推送，应停止在“本地成果已准备好”的状态，给出 VS Code 推送步骤；只有用户明确要求继续且接受额外 token 成本时，才进入认证排障。

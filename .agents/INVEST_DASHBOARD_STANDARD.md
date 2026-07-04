# 投研数据页标准流程

用途：后续 agent 维护本项目时优先读取本文，按固定流程更新数据、生成图表、发布 GitHub Pages，减少重复解释和 token 消耗。

## 项目定位

- 工作目录：`/Users/jianfeng/Documents/投研助手`
- 本地预览：`site/index.html`
- GitHub 仓库：`lakersfengjian-star/invdata`
- GitHub Pages：`https://lakersfengjian-star.github.io/invdata/`
- 图表文件统一放在：`output/charts/`
- Pages 发布目录统一放在：`site/`
- Pages 图片目录统一放在：`site/assets/charts/`

## 核心原则

1. 时间序列优先本地存储，不要每次全量重新抓取。
2. 后续更新只补充“本地已有最大日期之后”的最新交易日数据。
3. 本地完整刷新成功后，再生成静态网页和 PNG。
4. GitHub Pages 发布尽量使用本地已生成/已落盘的汇总数据，避免在 Actions 中在线抓全市场行情。
5. 所有图表标题和网页标题必须展示最新数据日期，尤其是图三和图四。
6. 当净流入为 0 或关键字段缺失时，在页面注释中保留“数据可能未更新”的风险提示。
7. 严格执行 `TOKEN_EFFICIENT_WORKFLOW.md`：禁止通过对话或连接器搬运大型 base64、历史 CSV 或完整快照，优先本地增量、离线构建和正常 git 推送。

## 数据分层

### 原始/缓存数据

- `data/raw/`：手工或外部导入数据，例如 Wind PE_TTM 模板。
- `.work/cache/`：接口缓存与逐股日行情缓存，不作为 Pages 必需发布内容。

### 可复用时间序列

以下文件是后续增量更新的基础，应优先读取并只补最新日期：

- `data/processed/index_close.csv`
- `data/processed/etf_daily_flow_detail.csv`
- `data/processed/broad_etf_flow.csv`
- `data/processed/star50_etf_flow.csv`
- `data/processed/a_share_turnover_concentration.csv`
- `data/processed/index_pe_ttm_valuation.csv`
- `data/processed/metadata.json`

逐股明细 `data/processed/a_share_daily_turnover_rank_detail.csv` 很大，只在本地保留；发布时优先使用汇总表 `a_share_turnover_concentration.csv`。

## 数据源优先级

1. 交易所及公开接口：上交所 ETF 历史规模、公开行情 K 线、交易所或行情站点公开数据。
2. AkShare：ETF 单位净值、A股代码表、公开估值封装接口等。
3. Tushare/Wind/本地 CSV：当公开源缺失时使用。深交所 ETF 历史份额和万得全A PE_TTM 可走此层。

## 标准更新流程

### 1. 检查本地状态

```bash
git status --short
ls data/processed
ls output/charts
```

不要回滚用户已有改动。若已有未提交变更，继续工作但避免覆盖无关文件。

### 2. 读取最新本地日期

优先查看：

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path("data/processed/metadata.json")
print(json.loads(p.read_text()).get("latest_common_date") if p.exists() else "no metadata")
PY
```

如果本地最新日期已经等于最新可用交易日，只需重建页面，不要全量抓取。

### 3. 增量抓取数据

当前主脚本为：

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache MPLCONFIGDIR=/tmp/matplotlib-cache /Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_etf_dashboard.py
```

后续优化方向：

- 先读取本地 CSV 的最大日期。
- 只请求最大日期之后到最新可用交易日的数据。
- 对逐股成交额使用 `.work/cache/sina_a_share_daily_2026/` 缓存，已有个股文件只补缺口。
- 对 ETF 份额、NAV、指数收盘价保留按日期缓存，避免重复访问历史区间。

### 4. 离线重建网页

本地汇总数据齐全后，优先用离线脚本重建网页和发布目录：

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache MPLCONFIGDIR=/tmp/matplotlib-cache /Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build_site_from_processed.py
```

该脚本只读取 `data/processed` 中的小型汇总表，生成：

- `output/charts/*.png`
- `site/index.html`
- `site/assets/charts/*.png`

### 5. 本地核验

必须确认：

```bash
rg -n "assets/charts|截至|区间|图三|图四" site/index.html
find site/assets/charts -maxdepth 1 -type f -print | sort
```

期望：

- 页面图片路径为 `assets/charts/...`
- 图一、图二最新日期与 `metadata.json` 一致
- 图三标题包含 `截至YYYY-MM-DD`
- 图四每张标题包含 `截至YYYY-MM-DD`
- `site/assets/charts/` 至少有 5 张 PNG

### 6. GitHub Pages 发布

`.github/workflows/pages.yml` 应发布 `site` 目录，而不是整个仓库：

```yaml
- name: Build dashboard
  run: python scripts/build_site_from_processed.py
- name: Upload artifact
  uses: actions/upload-pages-artifact@v3
  with:
    path: site
```

这样线上页面根目录就是 `site/index.html` 内容，图片路径可直接使用 `assets/charts/...`。

发布优先使用正常 git 流程提交本地变更。若本机 GitHub 凭证不可用，使用 GitHub 连接器时只更新小文件；不要再逐段上传大型数据快照。需要大文件远端同步时，先向用户说明 token 成本并优先修复 git 凭证。

### 7. 线上核验

发布后检查：

```bash
curl -L -sS -o /tmp/invdata-page.html -w '%{http_code} %{url_effective}\n' https://lakersfengjian-star.github.io/invdata/
rg -n "assets/charts|截至|区间" /tmp/invdata-page.html
curl -L -sS -o /tmp/chart.png -w '%{http_code} %{size_download}\n' https://lakersfengjian-star.github.io/invdata/assets/charts/fig_001_broad_etf_flow.png
```

期望：

- 首页 HTTP `200`
- 页面中不再出现 `../output/charts`
- 图片 HTTP `200` 且下载大小明显大于 10KB

## 图表编号

- `fig_001_broad_etf_flow.png`：沪深300/上证指数与大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数与科创50ETF资金流
- `fig_003_a_share_turnover_concentration.png`：A股成交额前10/前100交易集中度
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300指数 PE_TTM 标准差通道
- `fig_004b_sse_pe_ttm_channel.png`：上证指数 PE_TTM 标准差通道
- `fig_004c_wind_all_a_pe_ttm_channel.png`：万得全A PE_TTM 标准差通道，依赖本地 CSV
- `fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png`：万得全A除金融石油石化 PE_TTM 标准差通道，依赖本地 CSV
- `fig_005_index_amount_share.png`：沪深300、中证500、中证1000、中证2000成交额占全A成交额比例。数据优先来自中证指数官网指数行情接口；中证全指成交金额暂作为 Wind 全A成交额公开代理口径，后续若接入 Wind/Tushare 精确 Wind 全A成交额，可替换分母。

## 页面分类区域

网页必须按六个固定区域组织，并通过顶部分类按钮切换展示：

- 行情：指数走势、市场价格、ETF资金流等行情联动图。当前包含图一、图二、图五。
- 宏观：利率、通胀、信用、经济增长、政策等宏观指标。当前为空位。
- 估值：PE、PB、ERP、标准差通道、估值分位等指标。当前包含图四系列。
- 盈利：ROE、利润增速、收入增速、盈利预测、财报汇总等指标。当前为空位。
- 流动性：成交额、成交集中度、资金流、融资融券、市场流动性指标。当前包含图三。
- 情绪：换手、涨跌停、风险偏好、拥挤度、舆情或情绪指标。当前为空位。

新增指标时，优先判断其所属分类，在 `scripts/build_site_from_processed.py` 和 `scripts/update_etf_dashboard.py` 的对应 `category-panel` 中追加图表，不要重新创建新的一级分类，除非用户明确要求扩展分类体系。

## Wind PE_TTM 本地 CSV

路径：

```text
data/raw/index_pe_ttm_wind.csv
```

字段：

```csv
date,index_name,pe_ttm
2020-01-02,万得全A,18.2
2020-01-02,万得全A（除金融、石油石化）,24.5
```

## 后续增量优化 TODO

- 将 `scripts/update_etf_dashboard.py` 的全量抓取改为按本地最大日期增量补数。
- 为每个数据模块写入 `last_success_date`，避免接口失败时覆盖已有有效数据。
- 将 GitHub Pages 发布固定为离线构建，线上只依赖 `data/processed` 汇总文件。
- 大体量逐股明细不上传 GitHub；只上传汇总后的时间序列。

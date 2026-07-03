# 投研数据页固定指令

目标：维护一个可分享的静态投研页面，所有图表先由本地脚本生成 PNG/CSV，再发布到 GitHub Pages。

## 一句话触发

按固定指令更新 `/Users/jianfeng/Documents/投研助手` 的投研数据页，生成图表、更新 `site/index.html`，然后发布到 GitHub Pages。

## 运行方式

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_etf_dashboard.py
```

## 输出

- 页面入口：`index.html` -> `site/index.html`
- 图表目录：`output/charts/`
- 数据目录：`data/processed/`
- 元数据：`data/processed/metadata.json`

## 图表编号

- `fig_001_broad_etf_flow.png`：沪深300/上证指数与大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数与科创50ETF资金流
- `fig_003_a_share_turnover_concentration.png`：A股成交额前10/前100集中度
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300PE_TTM标准差通道
- `fig_004b_sse_pe_ttm_channel.png`：上证指数PE_TTM标准差通道
- `fig_004c_wind_all_a_pe_ttm_channel.png`：万得全A PE_TTM标准差通道，需本地CSV
- `fig_004d_wind_all_a_ex_fin_petchem_pe_ttm_channel.png`：万得全A除金融石油石化PE_TTM标准差通道，需本地CSV

## 数据源优先级

1. 交易所与公开接口。
2. AkShare 封装接口。
3. Tushare/Wind 或本地 CSV fallback。

## 本地 CSV fallback

Wind PE_TTM 文件：`data/raw/index_pe_ttm_wind.csv`

字段：

```csv
date,index_name,pe_ttm
2020-01-02,万得全A,18.2
2020-01-02,万得全A（除金融、石油石化）,24.5
```

## 发布

GitHub Pages 使用 `.github/workflows/pages.yml`。推送到 `main` 后，Actions 会把整个仓库作为静态站点发布。

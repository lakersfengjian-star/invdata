# 投研数据页面

当前页面输出两张 ETF 资金流图：

- `fig_001_broad_etf_flow.png`：沪深300与上证指数走势及大宽基ETF资金流
- `fig_002_star50_etf_flow.png`：科创50指数走势及科创50ETF资金流
- `fig_003_a_share_turnover_concentration.png`：A股成交额前10/前100交易集中度
- `fig_004a_hs300_pe_ttm_channel.png`：沪深300指数PE_TTM标准差通道
- `fig_004b_sse_pe_ttm_channel.png`：上证指数PE_TTM标准差通道

更新命令：

```bash
/Users/jianfeng/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/update_etf_dashboard.py
```

页面入口：

```text
site/index.html
```

数据口径：

- 区间从 `2025-01-01` 开始，截止到指数、ETF份额等核心数据共同可用的最新交易日。
- ETF净流入 = 当日份额变化 × 估值价格 / 1亿元。
- 估值价格优先使用 ETF 单位净值；单位净值缺失时，使用 ETF 二级市场收盘价估算。
- 7日滚动合计按交易日滚动计算。
- 当净流入为 0 或长时间缺失时，可能代表份额数据未更新或接口未披露。

数据源顺序：

1. 交易所及公开行情接口：上交所 ETF 历史规模、腾讯公开 K 线、东方财富 ETF 规模快照。
2. AkShare：ETF 单位净值等封装接口。
3. Tushare：脚本已预留 `TUSHARE_TOKEN` fallback；配置后可补深交所 ETF 历史份额。

估值图说明：

- 沪深300 PE_TTM 来自乐咕乐股指数估值接口。
- 上证指数 PE 使用乐咕市场估值接口；当前公开源历史点较稀疏。
- 万得全A、万得全A（除金融、石油石化）暂无稳定公开接口。可将 Wind 导出的数据保存为 `data/raw/index_pe_ttm_wind.csv`，字段为 `date,index_name,pe_ttm`，其中 `index_name` 分别填 `万得全A`、`万得全A（除金融、石油石化）`。

# Agents 文档索引

本目录用于保存后续 agent 维护投研数据页时需要优先读取的标准流程和问题核查文档。

- `INVEST_DASHBOARD_STANDARD.md`：标准更新、增量存储、Python 本地抓数、离线建站和 VS Code 发布边界。
- `ISSUE_CHECKLIST.md`：GitHub Pages、图片显示、数据日期、Actions 构建等问题核查清单。
- `TOKEN_EFFICIENT_WORKFLOW.md`：token 节省、低成本发布、禁止大文件对话搬运、禁止常规认证排障的强制规范。

后续接手任务时，先读以上三份文档，再执行数据更新或发布。若任务涉及 GitHub Pages、数据快照、图表生成或线上核验，必须同时遵守 token 节省规范。

新增图表需优先独立成 `scripts/update_<metric>.py`，本地落盘到 `data/processed/` 后再由 `scripts/build_site_from_processed.py` 统一生成页面。当前新增行业拥挤度图为 `fig_006_citic_industry_crowding.png`，Wind 不可用时读取 `data/raw/citic_industry_crowding_weekly.csv`。

行情板块新增指标继续按独立脚本维护：涨停观察表使用 `scripts/update_limit_up_tables.py`，TMT/红利低波成交额占比使用 `scripts/update_theme_amount_share.py`，全市场成交额变化使用 `scripts/update_market_turnover.py`。流动性板块南向资金每日净流入使用 `scripts/update_southbound_flow.py`。不要通过对话搬运逐股大表；只保留前十汇总表、主题成交额时间序列和南向资金汇总序列。

宏观板块图十使用 `scripts/update_macro_overview.py`。服务业和固投分项优先从国家统计局获取；社融和企业中长期贷款使用人民银行数据。缺口数据可用 `data/raw/macro_overview_extra.csv`、`data/raw/pbc_macro_credit.csv` 本地补充。

默认职责边界：

- agent：本地 Python 增量抓数、生成图表、重建 `site/`、最小核验、更新文档。
- VS Code：GitHub 登录、凭证、分支管理、Commit、Push、Sync、Actions 查看。
- 若推送或认证失败，agent 不再长时间排障；转为给出 VS Code 操作步骤，由用户在本地客户端完成。

# GitHub Pages 发布说明

本项目已经具备 GitHub Pages 静态站点结构：

- 页面入口：`site/index.html`
- 页面图片：`site/assets/charts/`
- 高分辨率图表备份：`output/charts/`
- Pages workflow：`.github/workflows/pages.yml`
- GitHub 仓库：`lakersfengjian-star/invdata`
- Pages 地址：`https://lakersfengjian-star.github.io/invdata/`

## 推荐发布方式

后续发布默认通过 VS Code Source Control 完成，不由 agent 长时间处理 GitHub 凭证。

1. agent 本地运行 Python 脚本，完成数据更新、图表生成和 `site/` 重建。
2. agent 给出最小核验结果和待提交文件范围。
3. 用户在 VS Code Source Control 中检查变更。
4. 用户在 VS Code 中 Commit/Push，VS Code 负责 GitHub 登录和 HTTPS 凭证。
5. GitHub Actions 自动发布 `site/`。

本地检查：

```bash
git status -sb
git log --oneline -3
```

如确需命令行推送：

```bash
git push origin HEAD:main
```

若命令行凭证失败，停止在 agent 会话中继续排障，改由 VS Code 登录和推送。

## Pages workflow 要求

`.github/workflows/pages.yml` 应发布 `site/` 目录：

```yaml
with:
  path: site
```

线上核验只做轻量检查：

```bash
curl -L -sS -o /tmp/invdata-page.html -w '%{http_code} %{url_effective}\n' https://lakersfengjian-star.github.io/invdata/
rg -n "assets/charts|截至|区间" /tmp/invdata-page.html
curl -L -sS -o /tmp/chart.png -w '%{http_code} %{size_download}\n' https://lakersfengjian-star.github.io/invdata/assets/charts/fig_005_index_amount_share.png
```

## 禁止事项

- 不通过聊天传输 PAT、密码或验证码。
- 不通过 GitHub 连接器上传大型 CSV、PNG、base64 快照。
- 不把 VS Code/GitHub 登录排障作为常规 agent 工作。
- 不为了发布反复读取大型数据文件或完整 Git 历史。

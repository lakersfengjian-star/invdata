# GitHub Pages 发布说明

本项目已经具备 GitHub Pages 静态站点结构：

- 根入口：`index.html`
- 实际页面：`site/index.html`
- 图片：`output/charts/`
- Pages workflow：`.github/workflows/pages.yml`

首次发布需要一个 GitHub 仓库，例如：

```bash
git init
git add .
git commit -m "Publish investment dashboard"
git branch -M main
git remote add origin git@github.com:<owner>/<repo>.git
git push -u origin main
```

发布地址通常为：

```text
https://<owner>.github.io/<repo>/
```

如果仓库名是 `<owner>.github.io`，地址为：

```text
https://<owner>.github.io/
```

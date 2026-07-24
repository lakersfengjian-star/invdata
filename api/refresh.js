const OWNER = "lakersfengjian-star";
const REPO = "invdata";
const WORKFLOW = "auto-update-dashboard.yml";
const REF = "main";

module.exports = async function handler(request, response) {
  if (request.method !== "POST") {
    response.setHeader("Allow", "POST");
    return response.status(405).json({ message: "Only POST is supported." });
  }

  const token = process.env.GITHUB_PAT || process.env.GITHUB_TOKEN;
  if (!token) {
    return response.status(500).json({
      message: "刷新密钥未配置，请在 Vercel 环境变量中配置 GITHUB_PAT。",
    });
  }

  const apiResponse = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: REF }),
    },
  );

  if (!apiResponse.ok) {
    const detail = await apiResponse.text();
    return response.status(apiResponse.status).json({
      message: "GitHub 自动刷新任务提交失败。",
      detail,
    });
  }

  return response.status(202).json({
    message: "刷新任务已提交。",
    workflow: WORKFLOW,
    ref: REF,
  });
};

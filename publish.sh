#!/usr/bin/env bash
# 将「科学前沿」发布到运行者自己的 GitHub 账户。仅在本地授权，不收集/输出任何令牌。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO_NAME="${1:-science-frontier}"
if ! [[ "$REPO_NAME" =~ ^[a-zA-Z0-9._-]+$ ]]; then
  echo '错误：仓库名称只能包含英文、数字、点、下划线或连字符。' >&2
  exit 2
fi
for cmd in git gh; do
  if ! command -v "$cmd" >/dev/null; then
    echo "缺少 $cmd。Mac 可先运行：brew install git gh" >&2
    exit 2
  fi
done
if ! gh auth status >/dev/null 2>&1; then
  echo '正在调用 GitHub 官方授权（不要在聊天中发送密码、令牌或验证码）。'
  gh auth login --hostname github.com --web --scopes repo,workflow
fi
OWNER="$(gh api user --jq .login)"
USER_ID="$(gh api user --jq .id)"
if gh repo view "$OWNER/$REPO_NAME" >/dev/null 2>&1; then
  echo "仓库 https://github.com/$OWNER/$REPO_NAME 已存在。为防止覆盖，脚本已停止。" >&2
  exit 2
fi
if [ -d .git ]; then
  echo '发现现有 Git 仓库。为防止误发布已有代码，脚本已停止。' >&2
  exit 2
fi
# 用户自己的仓库，限制 Git 身份配置在该仓库；不更改全局设置。
git init -b main
git config user.name "$OWNER"
git config user.email "$USER_ID+$OWNER@users.noreply.github.com"
git add .
git commit -m 'Launch Scientific Frontiers website and weekly digest'
echo '将创建公开 GitHub 仓库，并通过 HTTPS 发布本项目。'
gh repo create "$REPO_NAME" --public --source . --remote origin --push
if gh api "repos/$OWNER/$REPO_NAME/pages" >/dev/null 2>&1; then
  echo 'GitHub Pages 已配置。'
else
  if ! gh api --method POST "repos/$OWNER/$REPO_NAME/pages" -f build_type=workflow >/dev/null; then
    echo '自动开通 Pages 失败。请前往仓库 Settings → Pages，将 Source 设为 GitHub Actions。' >&2
  fi
fi
# 首次推送时 Pages 可能尚未开通，因此再次手动触发部署。
if ! gh workflow run deploy.yml --repo "$OWNER/$REPO_NAME" --ref main; then
  echo '首次触发部署失败。可从仓库 Actions 页面手动运行 Deploy Scientific Frontiers。' >&2
fi
# 初次发布后补录首期尚缺的专题；即使失败也不影响已部署网站。
if ! gh workflow run weekly.yml --repo "$OWNER/$REPO_NAME" --ref main; then
  echo '首次文献增补任务尚未触发；请到 Actions 手动运行 Science Frontier weekly digest。' >&2
fi
printf '\n仓库：https://github.com/%s/%s\n预期网站：https://%s.github.io/%s/\n' "$OWNER" "$REPO_NAME" "$OWNER" "$REPO_NAME"
echo '请打开仓库的 Actions 页面，确认 Deploy Scientific Frontiers 绿色成功后再访问网站。'
echo '如需自动生成六维中文分析：Settings → Secrets and variables → Actions → New repository secret，填写 OPENAI_API_KEY。'

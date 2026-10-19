# 科学前沿 · Scientific Frontiers

一个可公开访问、每周自动整理研究论文并保存历史周刊的中文静态网站，聚焦 Nature、Cell、Science 的生物医学/生信原始研究，以及眼科一区、单细胞测序与空间转录组一区、干眼一区/二区专题。每篇文章可记录标题、六维研究分析、DOI、PMID（如收录）和原始文献链接。

## 重要：当前交付状态

- **已有**：完整的响应式网页、2026-W42 首期精选论文（含经出版商页面核验的 SpatialZoomer 空间组学研究）、历史周刊文件、跨期检索、浏览器本地收藏、CSV 导出、Python 更新器、自动部署/定时更新工作流。
- **未自动完成**：创建用户的 GitHub 仓库、在 GitHub 中开启 Pages、正式部署域名、绑定有资费的 AI API Key。这些操作需要 GitHub 账户授权，不能仅凭下载文件完成。
- **论文解读**：未配置 API Key 时只更新可追溯论文元数据，新论文的六维分析显示“待解读”；配置后仅生成基于摘要的 AI 初稿，仍需人工核对全文。不得把自动摘要视作正式全文评审。
- **文献质量**：三本综合性主刊以准确刊名筛选；眼科及两个新专题参考**2025年中科院大类分区**（单细胞为一区；干眼为一区或二区；眼科一区）。中科院文献情报中心已宣布从2026年起不再更新分区表、平台于2026年9月30日停止服务。此名单是编辑维护的检索白名单，不能替代正式分区证明。部分论文因全文/元数据索引延迟可能被漏检。

## 最省事的上线方案（Mac）

1. 申请或登录 GitHub 账户：[https://github.com](https://github.com)。把完整 ZIP 解压，进入 `science-frontier/` 目录。
2. Mac 安装 GitHub CLI：在终端运行 `brew install gh`（若已有可跳过）；确保 `git` 命令可用。
3. 在这个文件夹打开终端，运行：

   ```bash
   bash publish.sh
   ```

   脚本将调用 GitHub 官方浏览器授权，以**你的 GitHub 账户**创建新的公开仓库 `science-frontier`，上传网站与自动化配置、尝试开启 GitHub Pages，并启动第一次部署。可指定不同仓库名：`bash publish.sh science-frontier-journal`。**不要在聊天中分享 GitHub 密码、PAT、API Key。**
4. 到仓库的 **Actions → Deploy Scientific Frontiers** 查看运行结果。部署成功后网址一般为：

   `https://<你的GitHub用户名>.github.io/science-frontier/`

   若脚本无法开通 GitHub Pages，在 GitHub 仓库 **Settings → Pages → Build and deployment → Source → GitHub Actions** 手动选定即可；随后在 Actions 手动运行 `Deploy Scientific Frontiers`。GitHub Free 账户使用 Pages 的此方案通常要求**仓库公开**。
5. 每周更新需要 GitHub 仓库 **Settings → Actions → General → Workflow permissions** 的 `Read and write permissions`。然后在 Actions 中确认 `Science Frontier weekly digest` 已启用。北京时间每周一及周三 **10:17（预计值，Actions 可能延迟）** 运行；周三作为首次抓取失败时的补偿重试。成功后，部署流程会自动再次发布网页。首次发布建议立刻在 Actions 手动运行一次 **Science Frontier weekly digest**，使升级前的 W42 周刊增补新专题。
6. 若想自动生成每篇论文的六维中文分析初稿，请通过仓库的 **Settings → Secrets and variables → Actions → New repository secret** 添加名为 `OPENAI_API_KEY` 的密钥。此举需要自行拥有 API 额度并承担费用；**不配置密钥也能每周自动收录论文，只是没有新论文的六维分析**。模型由 `.github/workflows/weekly.yml` 中 `OPENAI_MODEL` 指定，可以根据账户权限修改。

## 更新与历史归档机制

- Python 脚本以最近一个**完整周（周一至周日）**为抓取窗口；定时启动即自动获取 Europe PMC 元数据，随后严格按刊名、领域关键词、研究类型与 DOI 去重；可能有误收或漏收，正式发布建议人工审校。
- 归档写入 `data/issues/YYYY-Www.json`，首页读取 `data/latest.json`；`data/archive.json` 是历史周刊索引，`data/all.json` 是全部既往论文的跨周搜索索引（DOI 去重）。
- 如果某周已经归档，**默认不覆盖**，防止丢失旧内容。旧版档案如果带有 `topicBackfillComplete=false`，允许自动增补一次新专题，成功后自动标记已补录；不会清空原有六维解读。手动增补可使用 `--extend-issue`，完全重建才使用 `--refresh`。
- 如果有期刊接口故障导致抓取不完整，本次不会发布残缺周刊。成功抓取后才更新发布文件。
- 既往周刊保存在 GitHub 仓库和 Git 历史中；**只要仓库及其历史文件得到维护，便可长期回看**，但平台并不作“永久保存”承诺。建议定期备份仓库。
- “我的收藏”保存在当前浏览器的 `localStorage`；这**不是跨设备同步账户**，清除浏览器数据会清除收藏。论文原始历史数据不受此影响。

## 本地预览

```bash
python3 -m http.server 8000
```

浏览器进入 `http://localhost:8000`。离线演示也可打开 `科学前沿-单文件演示版.html`，但它只包含 2026-W42 首期示例（包含最新专题页面），无法自动更新或加载历史。

## 手动更新

```bash
python3 -m pip install -r requirements.txt
python3 update.py                    # 更新上一个完整周
python3 update.py --start 2026-10-19 # 更新指定完整周（周一）
python3 update.py --rebuild-index    # 仅重建跨期检索索引，不联网
python3 update.py --start 2026-10-12 --extend-issue  # 补录首期两项新专题（保留已有解读）
python3 update.py --start 2026-10-12 --refresh  # 人工明确覆盖已有周刊，谨慎使用
```

外部 API 并非绝对稳定，新论文入库可能有延迟。机器生成六维解读使用标题/摘要，不包含付费全文解析。建议后续增加审核状态、编辑界面及全文证据引用。

## 核心文件

- `index.html` / `app.js` / `styles.css`：静态网页与交互；搜索全部历史时按 40 篇分页展示。
- `data/latest.json` / `data/all.json` / `data/issues/*.json`：论文记录与归档。
- `journal_policy.json`：中科院2025年最后一版的大类分区候选期刊名单（单细胞一区、干眼一区和二区、眼科一区），包含核对来源；不与 JCR 混用。
- `update.py`：Europe PMC 期刊搜索、主题关键词过滤、DOI 合并多重栏目、AI 初稿与历史保存。
- `.github/workflows/weekly.yml`：每周定时更新；默认不覆盖已保存周刊。
- `.github/workflows/deploy.yml`：首次推送及每次周刊更新完成后自动发布 GitHub Pages。
- `publish.sh`：在用户本机通过 GitHub CLI 交互授权并初始化自己的正式网站。

## 数据规范

论文的 `reviewStatus` 表示 `metadata_only` 或 `abstract_only`；首期精选标为 `mode: curated`（人工整理初读，并非完整全文审核）。不以预印本 PMID 代替正式期刊文章的 PMID；未核验到的 PMID 留空。网页 DOI 链接指向 DOI 解析器。

注意：每个候选期刊单周最多入库12篇命中研究（命令行参数可调），关键词初筛可能漏收部分研究；当周无论文不等于该领域无研究。首期的干眼专题尚未全量补录，网页会显示补录中的提示。

所有新刊分析内容仅供科研选题和文献导航，不能替代审阅完整论文、补充材料和同行评议。

## 正式上线核验清单（首次部署后）

1. 打开 GitHub Pages URL，确认栏目 `单细胞测序与空间转录组`、`干眼` 可分别筛选，论文详情中显示 CAS2025 参考分区、DOI 和 PMID。
2. 运行 GitHub Actions 的 `Science Frontier weekly digest`；**最初无密钥也能新增文献元数据**。查看 Actions 日志中各期刊数据量，并确认 `data/issues/2026-W42.json` 被安全增补。
3. 在 `data/all.json` 核对 DOI 唯一性，在网页历史下拉框中切换到 `全部历史·跨期搜索`。
4. 单击 DOI 原文链接确保指向正式出版商论文，而不是预印本；PMID 若未收录保持空值。
5. 使用第二台设备访问公开网址。收藏在各浏览器独立保存，需要跨设备同步必须另加用户账号数据库。
6. 推荐将 GitHub 仓库设为定期备份源。不要把任何 GitHub Token、OpenAI API Key 或其他密钥提交到仓库。

期刊参考核验来源：中国科学院文献情报中心期刊分区表 [校外通知](https://www.lib.szu.edu.cn/er/fenqubiao)、候选期刊大类分区人工整理页面（各期刊见 `journal_policy.json`）。仅对原始研究进行自动六维解读；综述、勘误和社论不作为常规收录目标。

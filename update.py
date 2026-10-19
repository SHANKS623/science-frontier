#!/usr/bin/env python3
"""科学前沿每周更新器。只获取可溯源出版数据；无 API Key 时不生成解读。"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path
import re
import sys
import time

import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
ENDPOINT = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'

# 注意：使用 EXACT 期刊名称；Nature Communications / Cell Reports 不混入三大主刊。
TOP_JOURNALS = {'Nature': 'Nature', 'Cell': 'Cell', 'Science': 'Science'}
# 期刊分区基准：中科院2025年最后一版大类分区；不是JCR分区。
# 中科院2025年最后一期大类分区。由人工维护来源/名单，不能据此推断JCR分区。
POLICY = json.loads((ROOT / 'journal_policy.json').read_text(encoding='utf-8'))
EYE_JOURNALS = POLICY['eye']
SINGLE_JOURNALS = POLICY['singleCell']
DRY_EYE_JOURNALS = POLICY['dryEye']
# 命名策略：一篇文章可以同时属于主刊、眼科、单细胞、干眼专题；按 DOI 去重。
SINGLE_TERMS = re.compile(
    r'scRNA[\s-]?seq|snRNA[\s-]?seq|scATAC[\s-]?seq|snATAC[\s-]?seq|'
    r'single[\s-]?cell(?:ular)?[\s-]{0,3}(?:RNA|DNA|ATAC|sequenc|transcript|multi[\s-]?om|profil|atlas|resolu|omics)|'
    r'single[\s-]?nucle(?:us|i)[\s-]+(?:RNA|ATAC|sequenc|transcript|profil)|'
    r'spatial[\s-]+(?:transcriptom|multi[\s-]?om|omics|profil|RNA[\s-]?seq|genomic|proteomic)|'
    r'spatially[\s-]+resolved[\s-]+(?:transcript|omics|RNA)|'
    r'Visium|MERFISH|seqFISH|Xenium|Stereo[\s-]?seq|Slide[\s-]?seq|DBiT[\s-]?seq|'
    r'single[\s-]?cell[\s-]+sequencing|single[\s-]?cell[\s-]+resolution', re.I)
DRY_EYE_TERMS = re.compile(
    r'dry[\s-]?eye|keratoconjunctivitis[\s-]+sicca|meibomian[\s-]+gland|'
    r'meibomian[\s-]+dysfunction|\bMGD\b|tear[\s-]+film|tear[\s-]+secretion|'
    r'ocular[\s-]+surface[\s-]+(?:disease|inflamm|homeostas|disorder)|'
    r'lacrimal[\s-]+gland[\s-]+(?:dysfunction|inflamm|secretion|disease)|'
    r'sj[oö]gren[\s-]?s?[\s-]+syndrome', re.I)

TOP_TERMS = re.compile(
    r'cell|genom|genetic|rna|dna|protein|proteom|transcript|epigen|chromatin|immun|'
    r'cancer|tumou?r|disease|patient|human|tissue|bioinform|biolog|medicin|'
    r'enzyme|embryo|metaboli|microbi|drug|clinical|stem|neuro|brain|lipid|'
    r'receptor|bioengineering|virus|bacteri|biomolecul|aging|ageing|hematop|'
    r'organoid|inflamm|therap|evolution|mitochondri|gene|pathogen|single.cell|'
    r'organelle|pathophysio|microfluidic|antibod|hormone|fertil|microexon|'
    r'splicing|biomed|epithel|ecology|plant immun', re.I)
EXCLUDE_PUB = re.compile(r'review|editorial|comment|news|preprint|retract|correction|erratum|book|obituary|letter to the editor', re.I)
DOI_RE = re.compile(r'^10\.\d{4,9}/\S+$')
WEB_SESSION = requests.Session()
WEB_SESSION.headers.update({'User-Agent': 'ScientificFrontiersWeekly/1.0 (metadata research tool; contact via GitHub repository)', 'Accept': 'application/json'})


def monday_for_previous_complete_week(today: date) -> date:
    # 同一周只能在结束后归档；周一运行也抓取前一个完整周。
    return today - timedelta(days=today.weekday() + 7)


def strip_markup(text: str) -> str:
    text = re.sub(r'<[^>]*>', ' ', html.unescape(text or ''))
    return re.sub(r'\s+', ' ', text).strip()


def fetch_journal(journal: str, start: date, end: date) -> list[dict]:
    q = f'JOURNAL:"{journal}" AND FIRST_PDATE:[{start.isoformat()} TO {end.isoformat()}]'
    items = []
    cursor = '*'
    for _ in range(25):  # 显式控制上限；翻页不足时不能悄悄丢论文
        params = {'query': q, 'format': 'json', 'pageSize': 100, 'resultType': 'core', 'cursorMark': cursor}
        for attempt in range(3):
            try:
                r = WEB_SESSION.get(ENDPOINT, params=params, timeout=35)
                r.raise_for_status()
                data = r.json()
                break
            except (requests.RequestException, ValueError) as ex:
                if attempt == 2:
                    raise RuntimeError(f'抓取失败 {journal}: {ex}') from ex
                time.sleep(2 * (attempt + 1))
        items.extend(data.get('resultList', {}).get('result', []))
        nc = data.get('nextCursorMark')
        if not nc or nc == cursor or len(data.get('resultList', {}).get('result', [])) < 100:
            break
        cursor = nc
    else:
        raise RuntimeError(f'{journal} 本周结果超过分页安全上限，拒绝发布不完整周刊')
    return items


def sections_for(journal: str, text: str) -> list[str]:
    out = []
    if journal in TOP_JOURNALS:
        out.append(journal)
    if journal in EYE_JOURNALS:
        out.append('Eye')
    rank = (POLICY['journals'].get(journal) or {}).get('zone', 99)
    if journal in SINGLE_JOURNALS and rank == 1 and SINGLE_TERMS.search(text):
        out.append('SingleCell')
    if journal in DRY_EYE_JOURNALS and rank <= 2 and DRY_EYE_TERMS.search(text):
        out.append('DryEye')
    return out


def normalized_journal(s: str) -> str:
    return re.sub(r'[^a-z]', '', (s or '').lower()).removeprefix('the')


def is_original(item: dict) -> bool:
    types = (item.get('pubTypeList') or {}).get('pubType') or []
    if isinstance(types, str):
        types = [types]
    # 某些 Article 会被标为 Review / Editorial，同步排除。
    if any(EXCLUDE_PUB.search(str(t)) for t in types):
        return False
    title = item.get('title') or ''
    if re.match(r'^(Correction|Retraction|Erratum|Editorial|Author correction|Response to|Comment on)[: ]', title, re.I):
        return False
    if not item.get('doi') or not DOI_RE.match(item['doi'].strip()):
        return False
    return True


def item_as_paper(item: dict, group: str, journal: str) -> dict | None:
    # 精确验证期刊归属；不存在的 PMID 留空，严禁回退到预印本 PMID。
    actual_journal = item.get('journalTitle') or item.get('journalInfo', {}).get('journal', {}).get('title') or ''
    if normalized_journal(actual_journal.split('(')[0].strip()) != normalized_journal(journal):
        return None
    if not is_original(item):
        return None
    title = strip_markup(item.get('title', ''))
    abstract = strip_markup(item.get('abstractText', ''))
    content = title + ' ' + abstract
    sections = sections_for(journal, content)
    if not sections:
        return None
    # 三大主刊仅生物医学与生信；不引入无关物理/社会科学稿件。
    if journal in TOP_JOURNALS and not TOP_TERMS.search(content):
        return None
    # 主题期刊不因为刊名本身而全部收录，必须命中具体研究内容。
    if journal not in TOP_JOURNALS and journal not in EYE_JOURNALS and not any(x in sections for x in ('SingleCell', 'DryEye')):
        return None
    group = journal if journal in TOP_JOURNALS else ('Eye' if 'Eye' in sections else ('SingleCell' if 'SingleCell' in sections else 'DryEye'))
    pub = item.get('firstPublicationDate') or item.get('firstIndexDate') or item.get('firstPublicationDate')
    if not pub:
        return None
    pub = pub[:10]
    pub_type = (item.get('pubTypeList') or {}).get('pubType') or []
    if isinstance(pub_type, str):
        pub_type = [pub_type]
    # Europe PMC: source MED + 数字 id 对应正式发表论文的 PMID；其他来源不能臆造。
    pid = item.get('id', '')
    pmid = str(pid) if item.get('source') == 'MED' and str(pid).isdigit() else None
    doi = item['doi'].strip()
    authors = strip_markup(item.get('authorString', ''))
    return {
        'id': 'doi-' + re.sub(r'[^a-zA-Z0-9]+', '-', doi).strip('-').lower(),
        'journal': journal, 'group': group, 'sections': sections, 'date': pub,
        'type': next((t for t in pub_type if t.lower() not in ('journal article', 'article')), 'Research Article'),
        'title': title, 'zh': '', 'authors': authors, 'doi': doi, 'pmid': pmid,
        'url': 'https://doi.org/' + doi, 'tags': [], 'abstract': abstract,
        'rankSystem': 'CAS', 'rankEdition': POLICY['edition'],
        'rankZone': (POLICY['journals'].get(journal) or {}).get('zone'),
        'finding': '', 'why': '', 'problem': '', 'innovation': '', 'limitations': '', 'next': '',
        'reviewStatus': 'metadata_only'
    }


def existing_by_doi() -> dict[str, dict]:
    found = {}
    for fn in [DATA / 'latest.json', *sorted((DATA / 'issues').glob('*.json'))]:
        try:
            for p in json.loads(fn.read_text(encoding='utf-8')).get('papers', []):
                if p.get('doi'):
                    found[p['doi'].lower()] = p
        except (OSError, ValueError, KeyError):
            continue
    return found


def generate_brief(client, model: str, paper: dict) -> dict:
    if not paper.get('abstract'):
        return {}
    instructions = (
        '你是严谨的生物医学期刊编辑。仅根据提供的标题与摘要，以中文生成结构化的短评。'
        '不要假称阅读全文；不要编造数值、样本量、动物实验、机制、DOI 或 PMID。'
        '分清作者已实证的发现与未来研究设想。'
        '如果摘要没有支持某种局限，表述为合理但需要全文核实的待验证限制。'
        '仅输出 JSON 对象，包含字段 zh, finding, why, problem, innovation, limitations, next, tags；'
        '前六个字段为各 1–3 句，zh 是中文标题，tags 为最多三个简短中文标签。'
        '如果重要信息不足，明确说「摘要尚不足以判断」。'
    )
    content = f"Journal: {paper['journal']}\nTitle: {paper['title']}\nDate: {paper['date']}\nAbstract: {paper['abstract']}"
    resp = client.chat.completions.create(
        model=model, temperature=0.2, response_format={'type': 'json_object'},
        messages=[{'role': 'system', 'content': instructions}, {'role': 'user', 'content': content}]
    )
    raw = resp.choices[0].message.content or '{}'
    parsed = json.loads(raw)
    keys = ['zh', 'finding', 'why', 'problem', 'innovation', 'limitations', 'next']
    clean = {k: strip_markup(parsed.get(k))[:850] for k in keys if isinstance(parsed.get(k), str)}
    clean['tags'] = [strip_markup(x)[:26] for x in parsed.get('tags', [])[:3] if isinstance(x, str)] if isinstance(parsed.get('tags'), list) else []
    clean['reviewStatus'] = 'abstract_only'
    return clean


def write_archives_and_catalog():
    """Build a cumulative, DOI-deduplicated catalog from immutable weekly issues."""
    archives = []
    all_papers = []
    seen_dois = set()
    sources = sorted((DATA / 'issues').glob('*.json'), reverse=True)
    for path in sources:
        try:
            issue = json.loads(path.read_text(encoding='utf-8'))
            archives.append({k: issue[k] for k in ('issue', 'weekStart', 'weekEnd')} |
                            {'file': 'data/issues/' + path.name})
            for paper in issue['papers']:
                doi = (paper.get('doi') or '').casefold().strip()
                if not doi:
                    continue
                if doi in seen_dois:
                    existing_item = next((x for x in all_papers if x.get('doi', '').casefold().strip() == doi), None)
                    if existing_item:
                        existing_item['sections'] = sorted(set(existing_item.get('sections', [existing_item.get('group')])) | set(paper.get('sections', [paper.get('group')])))
                    continue
                seen_dois.add(doi)
                item = dict(paper)
                item['originIssue'] = issue['issue']
                item['sourceMode'] = issue.get('mode', 'metadata')
                all_papers.append(item)
        except (KeyError, ValueError, OSError, TypeError) as ex:
            print(f'警告：跳过损坏的历史文件 {path}: {ex}', file=sys.stderr)
            continue
    all_papers.sort(key=lambda x: (x.get('date', ''), x.get('journal', '')), reverse=True)
    (DATA / 'archive.json').write_text(json.dumps(archives, ensure_ascii=False, indent=2), encoding='utf-8')
    if archives:
        catalog = {
            'issue': 'ALL', 'weekStart': archives[-1]['weekStart'],
            'weekEnd': archives[0]['weekEnd'],
            'generatedAt': datetime.now(timezone.utc).date().isoformat(),
            'mode': 'archive',
            'editorialNote': '跨期索引包含全部历史周刊，按 DOI 去重。解读质量以单篇证据等级为准。',
            'papers': all_papers,
        }
        (DATA / 'all.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
    return len(all_papers)


def process(start: date, limit: int, enrich: bool, regenerate: bool, refresh: bool = False, extend: bool = False):
    end = start + timedelta(days=6)
    issue_year, issue_num, _ = start.isocalendar()
    issue = f'{issue_year}-W{issue_num:02d}'
    target = DATA / 'issues' / f'{issue}.json'
    if target.exists() and not (refresh or extend):
        # 升级旧网站时，旧周刊可能没有新专题；仅自动补齐一次，已补齐后不重复改写历史。
        try:
            saved_issue = json.loads(target.read_text(encoding='utf-8'))
            if isinstance(saved_issue.get('papers'), list) and not saved_issue.get('topicBackfillComplete', False):
                extend = True
                print(f'{issue} 为升级前存档：将增补单细胞和干眼专题，同时保留原先的论文解读。')
        except (OSError, ValueError):
            pass
        if not extend:
            print(f'本周刊 {issue} 已归档；默认不覆盖。如需重建请使用 --refresh。')
            return 0
    known = existing_by_doi()
    journal_names = list(dict.fromkeys([*TOP_JOURNALS, *EYE_JOURNALS, *SINGLE_JOURNALS, *DRY_EYE_JOURNALS]))
    journals = [(j if j in TOP_JOURNALS else 'Topic', j) for j in journal_names]
    papers = []
    errors = []
    seen = set()
    archived = None
    if extend and target.exists():
        archived = json.loads(target.read_text(encoding='utf-8'))
        # 增补模式不会清空原有六维解读与自选文献，只补充尚未收录的新论文。
        for original in archived.get('papers', []):
            original['sections'] = sections_for(original.get('journal', ''),
                                                (original.get('title') or '') + ' ' + (original.get('abstract') or '')) or [original.get('group', 'Eye')]
            papers.append(original)
            if original.get('doi'):
                seen.add(original['doi'].lower())
    for group, journal in journals:
        try:
            raw = fetch_journal(journal, start, end)
            n = 0
            for r in raw:
                p = item_as_paper(r, group, journal)
                if not p or not (start.isoformat() <= p['date'] <= end.isoformat()):
                    continue
                if p['doi'].lower() in seen:
                    prior = next((v for v in papers if v.get('doi', '').lower() == p['doi'].lower()), None)
                    if prior:
                        prior['sections'] = sorted(set(prior.get('sections', [prior.get('group')])) | set(p['sections']))
                        prior['rankSystem'] = p['rankSystem']
                        prior['rankEdition'] = p['rankEdition']
                        prior['rankZone'] = p['rankZone']
                    continue
                seen.add(p['doi'].lower())
                prev = known.get(p['doi'].lower())
                if prev and not regenerate:
                    for field in ('zh','finding','why','problem','innovation','limitations','next','tags'):
                        if prev.get(field):
                            p[field] = prev[field]
                    if p['finding']:
                        p['reviewStatus'] = prev.get('reviewStatus') or 'abstract_only'
                papers.append(p)
                n += 1
                if n >= limit:
                    break
            print(f'  {journal}: {n} 条')
        except Exception as ex:
            errors.append(str(ex))
            print(f'  WARNING {ex}', file=sys.stderr)
    if errors:
        print('部分期刊抓取失败，本次不发布可能不完整的周刊；请稍后重试。', file=sys.stderr)
        return 1
    papers.sort(key=lambda x: (x['date'], x['group'] == 'Eye'), reverse=True)
    if not papers:
        print('没有找到可核验的论文。已保留旧一期数据，避免把主页清空。', file=sys.stderr)
        return 1
    client = None
    if enrich and os.environ.get('OPENAI_API_KEY'):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=70, max_retries=2)
        except Exception as ex:
            print(f'AI 客户端不可用，进入仅元数据模式：{ex}', file=sys.stderr)
    if client:
        model = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
        for idx, p in enumerate(papers, 1):
            if p['finding'] and not regenerate:
                continue
            if not p.get('abstract'):
                continue
            try:
                p.update(generate_brief(client, model, p))
                print(f'  解析初稿 {idx}/{len(papers)}: {p["title"][:38]}')
            except Exception as ex:
                errors.append(f'AI 处理失败: {p["doi"]} {ex}')
                print(f'  WARNING AI 处理失败：{p["doi"]} {ex}', file=sys.stderr)
    # 为无 key 的新增论文保留空解读，不进行模板式的虚构结论。
    if papers:
        papers[0]['featured'] = True
    mode = 'enriched' if any(p.get('reviewStatus') == 'abstract_only' for p in papers) else 'metadata'
    payload = {
        'issue': issue, 'weekStart': start.isoformat(), 'weekEnd': end.isoformat(),
        'generatedAt': datetime.now(timezone.utc).date().isoformat(), 'mode': mode,
        'editorialNote': '自动抓取自 Europe PMC 的可溯源数据；主题期刊范围使用2025年中科院最后一版大类分区候选池，摘要AI初稿需人工审校；历史周刊默认不覆盖。',
        'rankPolicy': {'scheme':'CAS', 'edition':2025, 'basis':'large_category'},
        'topicBackfillComplete': True,
        'errors': errors, 'papers': papers,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'issues').mkdir(exist_ok=True)
    target = DATA / 'issues' / f'{issue}.json'
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        current_latest = json.loads((DATA / 'latest.json').read_text(encoding='utf-8'))
        overwrite_latest = current_latest.get('weekStart', '') <= start.isoformat()
    except (OSError, ValueError):
        overwrite_latest = True
    if overwrite_latest:
        (DATA / 'latest.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        (DATA / 'initial.js').write_text('window.__SCIENCE_INITIAL_DATA__ = ' + json.dumps(payload, ensure_ascii=False) + ';\n', encoding='utf-8')
    total = write_archives_and_catalog()
    print(f'已写入 {target} / {len(papers)} 篇；历史去重累计 {total} 篇；{len(errors)} 个警告。')
    return 0


def main():
    parser = argparse.ArgumentParser(description='更新「科学前沿」最新完整周刊')
    parser.add_argument('--start', help='指定期刊周刊开始日期（周一），YYYY-MM-DD；默认上个完整周')
    parser.add_argument('--max-per-journal', type=int, default=12, help='每期刊最多保留条数，默认 12')
    parser.add_argument('--no-ai', action='store_true', help='即使存在 OPENAI_API_KEY，也不生成解读')
    parser.add_argument('--regenerate', action='store_true', help='强制重新生成已有分析初稿（需配合 --refresh）')
    parser.add_argument('--refresh', action='store_true', help='明确允许重建某期历史周刊（谨慎使用）')
    parser.add_argument('--rebuild-index', action='store_true', help='仅重新生成历史目录及跨期检索索引，不联网')
    parser.add_argument('--extend-issue', action='store_true', help='增补已有周刊的专题内容；保留原有解读，并重新校验当周期刊')
    args = parser.parse_args()
    if args.rebuild_index:
        print(f'历史周刊去重收录 {write_archives_and_catalog()} 篇。')
        return 0
    start = date.fromisoformat(args.start) if args.start else monday_for_previous_complete_week(date.today())
    if start.weekday() != 0:
        parser.error('--start 必须指定周一')
    if args.max_per_journal < 1 or args.max_per_journal > 100:
        parser.error('--max-per-journal 限定在 1 到 100')
    print(f'科学前沿：准备收录 {start} 至 {start+timedelta(days=6)}')
    return process(start, args.max_per_journal, not args.no_ai, args.regenerate, args.refresh, args.extend_issue)


if __name__ == '__main__':
    raise SystemExit(main())

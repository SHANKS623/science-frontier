"""Offline safety checks for Science Frontier's weekly update and history."""
import json
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update


def test_previous_complete_week():
    assert update.monday_for_previous_complete_week(date(2026, 10, 19)) == date(2026, 10, 12)
    assert update.monday_for_previous_complete_week(date(2026, 10, 18)) == date(2026, 10, 5)


def test_existing_issue_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(update, 'DATA', tmp_path)
    issues = tmp_path / 'issues'
    issues.mkdir()
    target = issues / '2026-W42.json'
    target.write_text('{"sentinel":"keep me"}', encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('Existing weekly issue should not be fetched/overwritten')
    monkeypatch.setattr(update, 'fetch_journal', forbidden)
    assert update.process(date(2026, 10, 12), 12, False, False) == 0
    assert target.read_text(encoding='utf-8') == '{"sentinel":"keep me"}'


def test_all_issues_index_has_all_history_and_deduplicates_doi(tmp_path, monkeypatch):
    monkeypatch.setattr(update, 'DATA', tmp_path)
    issues = tmp_path / 'issues'
    issues.mkdir()
    def payload(issue, start, end, papers):
        return {'issue': issue, 'weekStart': start, 'weekEnd': end, 'mode': 'curated', 'papers': papers}
    (issues/'2026-W42.json').write_text(json.dumps(payload('2026-W42', '2026-10-12', '2026-10-18', [
        {'doi': '10.1000/A', 'date': '2026-10-13', 'title': 'Older', 'journal': 'Nature'}])), encoding='utf-8')
    (issues/'2026-W43.json').write_text(json.dumps(payload('2026-W43', '2026-10-19', '2026-10-25', [
        {'doi': '10.1000/a', 'date': '2026-10-20', 'title': 'Newer duplicate', 'journal': 'Nature'},
        {'doi': '10.1000/B', 'date': '2026-10-21', 'title': 'Other', 'journal': 'Cell'}])), encoding='utf-8')
    assert update.write_archives_and_catalog() == 2
    all_papers = json.loads((tmp_path/'all.json').read_text(encoding='utf-8'))
    assert all_papers['mode'] == 'archive'
    assert len(all_papers['papers']) == 2
    assert any(p['title'] == 'Newer duplicate' and p['originIssue'] == '2026-W43' for p in all_papers['papers'])
    assert len(json.loads((tmp_path/'archive.json').read_text(encoding='utf-8'))) == 2


def test_partial_fetch_failure_does_not_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(update, 'DATA', tmp_path)
    monkeypatch.setattr(update, 'TOP_JOURNALS', {'Nature': 'Nature', 'Cell': 'Cell'})
    monkeypatch.setattr(update, 'EYE_JOURNALS', [])
    def fake_fetch(journal, *args):
        if journal == 'Cell':
            raise RuntimeError('Source unavailable')
        return [{'journalTitle': 'Nature', 'title': 'Biology of cells', 'abstractText': 'Cell mechanism.',
                 'doi': '10.1000/abc', 'firstPublicationDate': '2026-10-12',
                 'source': 'MED', 'id': '12345678'}]
    monkeypatch.setattr(update, 'fetch_journal', fake_fetch)
    assert update.process(date(2026, 10, 12), 12, False, False) == 1
    assert not (tmp_path/'latest.json').exists()
    assert not (tmp_path/'issues'/'2026-W42.json').exists()

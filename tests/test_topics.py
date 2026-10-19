"""Offline, deterministic topic taxonomy and weekly-index regression tests."""
from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update


def fake_item(journal, title, abstract, pub='2026-10-14', doi='10.1000/test', pubtype=None):
    return {'journalTitle':journal,'title':title,'abstractText':abstract,
            'firstPublicationDate':pub,'doi':doi,'source':'MED','id':'42870000',
            'pubTypeList':{'pubType':pubtype or ['Journal Article']}}


def test_last_cas_edition_is_not_jcr():
    assert update.POLICY['scheme']=='CAS' and update.POLICY['edition']==2025
    assert update.POLICY['rankBasis']=='large_category'
    for journal in update.SINGLE_JOURNALS:
        assert update.POLICY['journals'][journal]['zone']==1
    for journal in update.DRY_EYE_JOURNALS:
        assert update.POLICY['journals'][journal]['zone']<=2
    for journal in update.EYE_JOURNALS:
        assert update.POLICY['journals'][journal]['zone']==1
    assert 'Cornea' not in update.DRY_EYE_JOURNALS


def test_single_cell_spatial_requires_method_and_zone1():
    hit=update.item_as_paper(fake_item('Nature Biomedical Engineering',
        'Spatial transcriptomics reveals tissue heterogeneity',
        'Single-cell resolution spatial transcriptomics at niche scales.'),
        'Topic','Nature Biomedical Engineering')
    assert hit['group']=='SingleCell'
    assert hit['sections']==['SingleCell']
    assert hit['rankZone']==1 and hit['rankEdition']==2025
    assert hit['pmid']=='42870000'
    assert update.item_as_paper(fake_item('Cell Systems',
        'A new cellular signaling system','Study of cellular metabolism in human tissue.'),
        'Topic','Cell Systems') is None


def test_dry_eye_only_allowed_journals_and_specific_topics():
    sample=fake_item('Investigative Ophthalmology & Visual Science',
        'Prospective evaluation of meibomian gland dysfunction',
        'Tear film stability in dry eye disease.')
    p=update.item_as_paper(sample,'Topic','Investigative Ophthalmology & Visual Science')
    assert p['sections']==['DryEye'] and p['rankZone']==2
    assert update.item_as_paper(fake_item('Cornea','Dry eye disease treatment','Meibomian glands.'),'Topic','Cornea') is None
    assert update.item_as_paper(fake_item('Chemical Engineering Journal',
        'A new catalyst in water', 'Conversion of industrial waste.'),'Topic','Chemical Engineering Journal') is None


def test_multiple_section_tags_without_extra_do_is():
    p=update.item_as_paper(fake_item('Nature',
        'Single-cell spatial transcriptomics in dry eye disease',
        'Spatial transcriptomics profiles the ocular surface.'), 'Nature','Nature')
    assert set(p['sections'])=={'Nature','SingleCell','DryEye'}
    assert p['group']=='Nature'


def test_review_and_preprints_excluded():
    it=fake_item('Nature Biomedical Engineering','Spatial transcriptomics review',
                 'Single-cell spatial transcriptomics',pubtype=['Review'])
    assert update.item_as_paper(it,'Topic','Nature Biomedical Engineering') is None
    it=fake_item('Nature Biomedical Engineering','Spatial transcriptomics',
                 'Single-cell spatial transcriptomics',pubtype=['Preprint'])
    assert update.item_as_paper(it,'Topic','Nature Biomedical Engineering') is None


def test_existing_archived_issue_preserved_on_topic_backfill(tmp_path,monkeypatch):
    monkeypatch.setattr(update, 'DATA', tmp_path)
    monkeypatch.setattr(update,'TOP_JOURNALS',{})
    monkeypatch.setattr(update,'EYE_JOURNALS',[])
    monkeypatch.setattr(update,'SINGLE_JOURNALS',['Nature Biomedical Engineering'])
    monkeypatch.setattr(update,'DRY_EYE_JOURNALS',['Investigative Ophthalmology & Visual Science'])
    issues=tmp_path/'issues';issues.mkdir()
    existing={'issue':'2026-W42','weekStart':'2026-10-12','weekEnd':'2026-10-18',
              'mode':'curated','topicBackfillComplete':False,
              'papers':[{'id':'legacy','doi':'10.1000/legacy','title':'Legacy paper',
                         'journal':'Nature Biomedical Engineering','group':'SingleCell',
                         'date':'2026-10-14','finding':'Important original editorial analysis'}]}
    file=issues/'2026-W42.json'
    file.write_text(json.dumps(existing))
    def fetch(journal,*args):
        if journal=='Nature Biomedical Engineering':
            return [fake_item(journal,'Spatial transcriptomics atlas',
                              'Single cell spatial omics analysis.',doi='10.1000/new')]
        return []
    monkeypatch.setattr(update,'fetch_journal',fetch)
    assert update.process(date(2026,10,12),12,False,False)==0
    latest=json.loads((tmp_path/'latest.json').read_text())
    assert latest['topicBackfillComplete'] is True
    assert len(latest['papers'])==2
    assert next(p for p in latest['papers'] if p['id']=='legacy')['finding']=='Important original editorial analysis'
    assert len(json.loads((tmp_path/'all.json').read_text())['papers'])==2
    def forbidden(*args):raise AssertionError('already backfilled should not fetch')
    monkeypatch.setattr(update,'fetch_journal',forbidden)
    assert update.process(date(2026,10,12),12,False,False)==0


def test_topic_fetch_failure_keeps_history_unchanged(tmp_path,monkeypatch):
    monkeypatch.setattr(update,'DATA',tmp_path)
    monkeypatch.setattr(update,'TOP_JOURNALS',{})
    monkeypatch.setattr(update,'EYE_JOURNALS',[])
    monkeypatch.setattr(update,'SINGLE_JOURNALS',['Nature Methods'])
    monkeypatch.setattr(update,'DRY_EYE_JOURNALS',[])
    issues=tmp_path/'issues';issues.mkdir()
    original={'issue':'2026-W42','weekStart':'2026-10-12','weekEnd':'2026-10-18',
              'topicBackfillComplete':False,'papers':[{'doi':'10.1000/old','journal':'Nature Methods','group':'SingleCell','title':'old'}]}
    f=issues/'2026-W42.json';prior=json.dumps(original)
    f.write_text(prior)
    def fail(*args):raise RuntimeError('API down')
    monkeypatch.setattr(update,'fetch_journal',fail)
    assert update.process(date(2026,10,12),12,False,False)==1
    assert f.read_text()==prior

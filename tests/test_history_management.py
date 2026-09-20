import pytest
from fastapi.testclient import TestClient
from test_service_api import enable_model

from jev_trader.api import create_app
from jev_trader.jobs import JobManager
from jev_trader.models import AnalysisError
from jev_trader.storage import Store


def saved_job(engine, identifier, status='paused', report=None):
    items = [] if report is None else [{"stock": {"symbol": report.symbol, "name": report.name, "market": report.market},
                                       "status": "ready", "data_status": "ready", "analysis_id": report.id,
                                       "action": report.action, "horizon": report.horizon, "error": None}]
    job = {"id": identifier, "created": 1, "scope": "watchlist", "phase": "analysis", "status": status,
           "items": items, "as_of": "2026-09-18", "error": None}
    engine.store.save_job(job)
    return job


def test_analysis_delete_restore_cache_and_scan_links(engine):
    calls = enable_model(engine)
    report = engine.analyze('000001')
    audit = engine.store.get(f'audit:{report.id}')
    with TestClient(create_app(engine.directory, engine)) as client:
        saved_job(engine, 'scan-with-report', 'completed', report)
        before = engine.provider.calls
        response = client.post('/api/analyses/delete', json={'ids': [report.id, report.id]})
        assert response.status_code == 200 and response.json()['count'] == 1
        token = response.json()['token']
        assert engine.store.summaries() == engine.store.history() == []
        assert client.get('/api/analyses/search').json()['total'] == 0
        assert client.get('/api/analyses?symbol=000001').json() == []
        assert client.get(f'/api/analyses/{report.id}').json()['code'] == 'analysis_missing'
        assert client.get(f'/api/analyses/{report.id}/export').status_code == 422
        item = client.get('/api/jobs/scan-with-report').json()['items'][0]
        assert item['analysis_id'] is None and item['analysis_deleted'] and item['action'] == report.action
        assert engine.provider.calls == before and len(calls) == 1
        # 迟到的写入以及进程重启不能取消删除标记。
        engine.store.save_analysis(report.model_dump(mode='json'))
        assert Store(engine.directory).analysis(report.id) is None
        replacement = engine.analyze('000001')
        assert replacement.id != report.id and len(calls) == 2
        assert engine.analyze('000001').id == replacement.id and len(calls) == 2
        assert client.post('/api/analyses/restore', json={'token': token}).json()['count'] == 1
        restored = engine.store.analysis(report.id)
        assert restored['created_at'] == report.created_at and restored['evidence'] == report.model_dump(mode='json')['evidence']
        assert engine.store.get(f'audit:{report.id}') == audit
        assert client.get('/api/jobs/scan-with-report').json()['items'][0]['analysis_id'] == report.id
        assert client.post('/api/analyses/restore', json={'token': token}).json()['count'] == 0


def test_scan_delete_keeps_reports_and_cache_and_can_be_undone(engine):
    calls = enable_model(engine)
    report = engine.analyze('000001')
    with TestClient(create_app(engine.directory, engine)) as client:
        job = saved_job(engine, 'old-paused', report=report)
        saved_job(engine, 'old-reset', 'reset', report)
        before = engine.provider.calls
        response = client.post('/api/jobs/delete', json={'ids': ['old-paused', 'old-reset']})
        assert response.status_code == 200 and response.json()['count'] == 2
        assert client.get('/api/jobs').json() == []
        assert client.get('/api/jobs/search').json()['total'] == 0
        assert client.get('/api/jobs/old-paused').json()['code'] == 'job_missing'
        assert client.post('/api/jobs/old-paused/resume', json={}).json()['code'] == 'job_missing'
        assert engine.store.analysis(report.id) and len(calls) == 1 and engine.provider.calls == before
        assert engine.analyze('000001').id == report.id and len(calls) == 1
        assert client.post('/api/jobs/restore', json={'token': response.json()['token']}).json()['count'] == 2
        assert engine.store.job('old-paused') == job
        assert client.get('/api/jobs/old-reset').json()['status'] == 'stopped'


@pytest.mark.parametrize('status', ['running', 'preparing', 'pausing', 'stopping', 'resetting'])
def test_running_scan_blocks_entire_selected_delete_batch(engine, status):
    with TestClient(create_app(engine.directory, engine)) as client:
        saved_job(engine, 'safe-paused')
        saved_job(engine, 'busy', status)
        response = client.post('/api/jobs/delete?lang=en', json={'ids': ['safe-paused', 'busy']})
        assert response.status_code == 422 and response.json()['code'] == 'job_active'
        assert engine.store.job('safe-paused') and engine.store.job('busy')
        assert not engine.store.deleted_ids('job')


def test_delete_is_atomic_validated_and_respects_local_write_guard(engine):
    report = engine.analyze('000001', technical_only=True)
    with TestClient(create_app(engine.directory, engine)) as client:
        for endpoint, ids in [('analyses', [report.id, 'missing']), ('jobs', ['missing'])]:
            assert client.post(f'/api/{endpoint}/delete', json={'ids': ids}).status_code == 422
        assert engine.store.analysis(report.id)
        for ids in [[], ['x'] * 101, [''], ['../outside'], ['a' * 129]]:
            assert client.post('/api/analyses/delete', json={'ids': ids}).status_code == 422
        assert client.post('/api/analyses/delete', json={'ids': [report.id]}, headers={'Origin': 'https://example.com'}).status_code == 403
        assert client.post('/api/jobs/restore', json={'token': 'bad-token'}).status_code == 422
        first = client.post('/api/analyses/delete', json={'ids': [report.id]}).json()
        second = client.post('/api/analyses/delete', json={'ids': [report.id]}).json()
        assert client.post('/api/analyses/restore', json={'token': first['token']}).json()['count'] == 0
        assert client.post('/api/jobs/restore', json={'token': second['token']}).json()['count'] == 0
        assert engine.store.analysis(report.id) is None
        assert client.post('/api/analyses/restore', json={'token': second['token']}).json()['count'] == 1


def test_another_manager_cannot_resume_a_deleted_paused_task(engine):
    enable_model(engine)
    manager = JobManager(engine)
    other = JobManager(engine)
    job = saved_job(engine, 'paused-before-delete')
    job['configuration'] = manager._configuration()
    engine.store.save_job(job)
    token = manager.delete([job['id']])['token']
    with pytest.raises(AnalysisError) as exc:
        other.resume(job['id'])
    assert exc.value.code == 'job_missing'
    manager.restore(token)
    assert other.get(job['id'])['status'] == 'paused'
    # 无关任务正在运行时仍可删除旧记录，且不影响运行任务。
    unrelated = saved_job(engine, 'unrelated', 'running')
    other.active = unrelated['id']
    assert manager.delete([job['id']])['count'] == 1
    assert other.get(unrelated['id'])['status'] == 'running'

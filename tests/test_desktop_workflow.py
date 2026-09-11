"""One full API workflow; all external services are replaced with local fakes."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from redpath.app import create_app
from redpath.config import Settings
from redpath.runtime import AppPaths
from redpath_ai import RuleBasedProvider
from redpath_kali.vm import ProcessResult
from redpath_kali.wsl_actions import WSLActionDispatcher
from redpath_setup.state import SetupStage


class FakeOllamaSetup:
    def inspect_service(self):
        return SetupStage('ollama', 'ready', 'OLLAMA_READY', 'Fake Ollama ready.')

    def inspect_model(self):
        return SetupStage('model', 'ready', 'MODEL_READY', 'Fake model ready.')


class FakeWslSetup:
    def __init__(self):
        self.calls = []

    def inspect_wsl(self):
        return SetupStage('wsl', 'ready', 'WSL_READY', 'Fake WSL ready.')

    def inspect_kali(self):
        return SetupStage('kali', 'ready', 'KALI_READY', 'Fake Kali ready.')

    def run_in_kali(self, arguments, timeout):
        assert tuple(arguments) == (
            'timeout', '--signal=KILL', '5s', 'nc', '-vz', '-w', '5',
            '192.168.56.20', '22',
        )
        assert timeout == 10
        self.calls.append((tuple(arguments), timeout))
        return ProcessResult(0, 'FAKE_RAW_OUTPUT', '')


class FakeModel(RuleBasedProvider):
    def recommend_next_step(self, context):
        # Exercise the model boundary with deterministic, valid local output.
        assert 'tryhackme' not in context.model_dump_json()
        assert '192.168.56.20' not in context.model_dump_json()
        return super().recommend_next_step(context)


@pytest.fixture
def desktop_client(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('External process or network access is forbidden in this workflow')

    monkeypatch.setattr('subprocess.run', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('socket.create_connection', forbidden)
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    paths = AppPaths.from_environment(str(tmp_path))
    app = create_app(Settings(database_url=f"sqlite:///{paths.database_file}"), paths)
    app.state.ollama_setup = FakeOllamaSetup()
    app.state.wsl_setup = FakeWslSetup()
    app.state.llm_provider = FakeModel()
    app.state.action_dispatcher = WSLActionDispatcher(app.state.wsl_setup)
    with TestClient(app) as client:
        yield client, app.state.wsl_setup


def test_complete_authorized_workflow(desktop_client):
    client, fake_wsl = desktop_client
    setup = client.get('/api/v1/setup')
    assert setup.status_code == 200
    assert all(stage['status'] == 'ready' for stage in setup.json()['components'].values())
    assert client.get('/').status_code == 200
    assert client.get('/api/v1/health').json()['database'] == 'ok'
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    session = client.post('/api/v1/sessions', json={
        'authorization_confirmed': True, 'expires_at': future,
    })
    assert session.status_code == 201
    route = f"/api/v1/sessions/{session.json()['id']}"
    assert client.post(f'{route}/lesson-source', json={
        'url': 'https://tryhackme.com/room/authorized-fixture',
    }).status_code == 201
    target = client.post(f'{route}/target', json={
        'address': '192.168.56.20', 'authorization_source': 'owned_training_lab',
        'expires_at': future,
    })
    assert target.status_code == 201
    scan = client.post(f'{route}/scan-import', json={
        'filename': 'nmap_sample.xml',
        'xml_text': (Path(__file__).parent / 'fixtures/nmap_sample.xml').read_text(),
    })
    assert scan.status_code == 201, scan.text
    assert scan.json()['findings']
    recommendation = client.post(f'{route}/recommendation')
    assert recommendation.status_code == 201, recommendation.text
    assert recommendation.json()['policy_decision']['allowed'] is True
    proposal = recommendation.json()['proposal']
    assert proposal['action_name'] == 'check_tcp_connection'
    assert proposal['arguments'] == {
        'target_id': target.json()['id'], 'port': 22, 'timeout_seconds': 5,
    }
    proposal_route = f"{route}/proposals/{proposal['id']}"
    assert client.post(f'{proposal_route}/run').status_code == 409
    assert fake_wsl.calls == []
    approval = client.post(f'{proposal_route}/approve')
    assert approval.status_code == 200
    result = client.post(f'{proposal_route}/run')
    assert result.status_code == 200, result.text
    assert result.json()['status'] == 'completed'
    assert result.json()['cleanup_status'] == 'completed'
    assert result.json()['evidence'][0]['target_address'] == '192.168.56.20'
    assert len(fake_wsl.calls) == 1
    assert client.post(f'{proposal_route}/run').status_code == 409
    assert len(fake_wsl.calls) == 1
    audit = client.get(f'{route}/audit-history?limit=100')
    assert audit.status_code == 200
    assert {'action.started', 'action.completed'} <= {
        event['event_type'] for event in audit.json()['events']
    }
    assert client.post(f'{route}/close').status_code == 200
    report = client.get(f'{route}/report')
    assert report.status_code == 200
    assert report.json()['session_state'] == 'completed'
    assert report.json()['execution_authorized'] is False
    assert report.json()['approvals'][0]['used'] is True
    assert report.json()['audit_event_count'] >= len(audit.json()['events'])
    for response in (result, audit, report):
        assert 'FAKE_RAW_OUTPUT' not in response.text

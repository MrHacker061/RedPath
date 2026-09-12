"""One full API workflow; all external services are replaced with local fakes."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from redpath.app import create_app
from redpath.config import Settings
from redpath.models import Action
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
def desktop_client(tmp_path, monkeypatch, security_config, client_options):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('External process or network access is forbidden in this workflow')

    monkeypatch.setattr('subprocess.run', forbidden)
    monkeypatch.setattr('subprocess.Popen', forbidden)
    monkeypatch.setattr('socket.create_connection', forbidden)
    monkeypatch.setattr('urllib.request.urlopen', forbidden)
    paths = AppPaths.from_environment(str(tmp_path))
    app = create_app(Settings(database_url=f"sqlite:///{paths.database_file}"), paths, security=security_config)
    app.state.ollama_setup = FakeOllamaSetup()
    app.state.wsl_setup = FakeWslSetup()
    app.state.llm_provider = FakeModel()
    app.state.action_dispatcher = WSLActionDispatcher(app.state.wsl_setup)
    with TestClient(app, **client_options) as client:
        yield client, app.state.wsl_setup


def create_approved_tcp_proposal(client, fake_wsl):
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
    approval_body = approval.json()
    assert approval_body['proposal_id'] == proposal['id']
    assert approval_body['approval_id']
    return route, target.json(), recommendation.json(), proposal, approval_body


def test_complete_authorized_workflow(desktop_client):
    client, fake_wsl = desktop_client
    setup = client.get('/api/v1/setup')
    assert setup.status_code == 200
    assert all(stage['status'] == 'ready' for stage in setup.json()['components'].values())
    assert client.get('/').status_code == 200
    assert client.get('/api/v1/health').json()['database'] == 'ok'
    route, target, recommendation, proposal, approval_body = create_approved_tcp_proposal(client, fake_wsl)
    proposal_route = f"{route}/proposals/{proposal['id']}"
    result = client.post(f'{proposal_route}/run')
    assert result.status_code == 200, result.text
    result_body = result.json()
    assert result_body['status'] == 'completed'
    assert result_body['cleanup_status'] == 'completed'
    assert result_body['evidence'][0]['target_address'] == '192.168.56.20'
    assert result_body['action_id']
    assert len(fake_wsl.calls) == 1
    assert client.post(f'{proposal_route}/run').status_code == 409
    assert len(fake_wsl.calls) == 1
    audit = client.get(f'{route}/audit-history?limit=100')
    assert audit.status_code == 200
    action_events = [
        event for event in audit.json()['events']
        if event['event_type'] in {'action.started', 'action.completed'}
    ]
    assert len(action_events) == 2
    assert [event['event_type'] for event in action_events].count('action.started') == 1
    assert [event['event_type'] for event in action_events].count('action.completed') == 1
    for event in action_events:
        details = event['details']
        assert details['action_id'] == result_body['action_id']
        assert details['proposal_id'] == proposal['id']
        assert details['approval_id'] == approval_body['approval_id']
    assert client.post(f'{route}/close').status_code == 200
    report = client.get(f'{route}/report')
    assert report.status_code == 200
    report_body = report.json()
    assert report_body['session_state'] == 'completed'
    assert report_body['execution_authorized'] is False
    assert report_body['proposals'] == [{
        'proposal_id': proposal['id'],
        'action_name': proposal['action_name'],
        'policy_allowed': True,
        'policy_code': recommendation['policy_decision']['code'],
    }]
    assert report_body['approvals'] == [{
        'proposal_id': proposal['id'],
        'status': 'approved',
        'expires_at': approval_body['expires_at'],
        'used': True,
    }]
    assert report_body['audit_event_count'] >= len(audit.json()['events'])
    for response in (result, audit, report):
        assert 'FAKE_RAW_OUTPUT' not in response.text


def test_action_claim_integrity_conflict_returns_409(desktop_client):
    client, fake_wsl = desktop_client
    route, _, _, proposal, _ = create_approved_tcp_proposal(client, fake_wsl)

    def conflict_on_action_flush(session, _flush_context, _instances):
        if any(isinstance(item, Action) for item in session.new):
            raise IntegrityError('INSERT actions', {}, RuntimeError('unique constraint'))

    event.listen(Session, 'before_flush', conflict_on_action_flush)
    try:
        response = client.post(f"{route}/proposals/{proposal['id']}/run")
    finally:
        event.remove(Session, 'before_flush', conflict_on_action_flush)

    assert response.status_code == 409
    assert response.json() == {'detail': 'Approval was already claimed'}

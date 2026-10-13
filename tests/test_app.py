import json
import shutil
import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import app as gateway


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(gateway, 'DB_PATH', tmp_path/'test.sqlite3')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('GATEWAY_BACKEND', 'cli')
    admin = gateway.setup_admin()
    client = TestClient(gateway.app)
    headers = {'X-Admin-Token': admin}
    r = client.post('/admin/keys', headers=headers, json={'label': 'test agent', 'rpm':2, 'monthly_limit':3})
    assert r.status_code == 200
    token = r.json()['key']
    return client, headers, {'Authorization': f'Bearer {token}'}, r.json()['id']


def test_dashboard_no_auth(context, monkeypatch):
    client, admin, auth, _kid = context
    monkeypatch.setattr(gateway, 'cli_auth_status', lambda: {'ready':True, 'detail':'ok'})
    assert client.get('/').status_code == 200
    assert client.get('/health').json()['configured'] is True
    assert client.get('/health').json()['backend'] == 'cli'
    assert client.get('/admin/keys').status_code == 401
    assert client.get('/v1/models').status_code == 401
    assert client.get('/v1/models', headers=auth).json()['data'][0]['id'] == 'sonnet'
    assert client.get('/admin/keys', headers=admin).json()['data'][0]['label'] == 'test agent'


def test_complete_and_anthropic_without_official_key(context, monkeypatch):
    client, admin, auth, _kid = context
    async def upstream(model, messages, max_tokens, system, temperature):
        assert model == 'sonnet'
        assert messages[-1]['content'] == 'Hello'
        return {'id':'msg_test','type':'message','role':'assistant','model':model,
                'content':[{'type':'text','text':'שלום'}],
                'stop_reason':'end_turn','usage':{'input_tokens':12,'output_tokens':3}}
    monkeypatch.setattr(gateway, 'upstream_call', upstream)
    payload = {'model':'sonnet','messages':[{'role':'user','content':'Hello'}]}
    r = client.post('/v1/chat/completions', json=payload, headers=auth)
    assert r.status_code == 200 and r.json()['choices'][0]['message']['content'] == 'שלום'
    assert r.json()['usage']['total_tokens'] == 15
    r = client.post('/v1/messages', json={**payload,'max_tokens':100}, headers=auth)
    assert r.status_code == 200 and r.json()['id'] == 'msg_test'
    assert client.get('/admin/logs', headers=admin).json()['data'][0]['input_tokens'] == 12


def test_limits_and_revoke(context, monkeypatch):
    client, admin, auth, kid = context
    async def fake(*_):
        return {'content':[{'type':'text','text':'ok'}], 'usage':{}}
    monkeypatch.setattr(gateway, 'upstream_call', fake)
    body = {'messages':[{'role':'user','content':'Hi'}]}
    assert client.post('/v1/chat/completions', json=body, headers=auth).status_code == 200
    assert client.post('/v1/chat/completions', json=body, headers=auth).status_code == 200
    assert client.post('/v1/chat/completions', json=body, headers=auth).status_code == 429
    assert client.post('/admin/keys/'+kid+'/revoke', headers=admin).json()['revoked']
    assert client.get('/v1/models', headers=auth).status_code == 401


def test_sessions_and_ownership(context, monkeypatch):
    client, admin, auth, _kid = context
    async def fake(*_):
        return {'content':[{'type':'text','text':'reply'}], 'usage':{}}
    monkeypatch.setattr(gateway,'upstream_call',fake)
    sid = client.post('/v1/sessions',headers=auth,json={'name':'My session','model':'haiku'}).json()['id']
    r=client.post('/v1/sessions/'+sid+'/messages',headers=auth,json={'message':'Test'})
    assert r.status_code==200 and r.json()['content']=='reply'
    assert len(client.get('/v1/sessions/'+sid,headers=auth).json()['messages'])==2
    assert client.delete('/admin/sessions/'+sid,headers=admin).status_code==200
    assert client.get('/v1/sessions/'+sid,headers=auth).status_code==404


def test_unsupported_features(context):
    client, _admin, auth, _kid = context
    body={'messages':[{'role':'user','content':'Hello'}], 'stream':True}
    assert client.post('/v1/chat/completions',headers=auth,json=body).status_code==400
    assert client.post('/v1/messages',headers=auth,json=body).status_code==400
    assert client.post('/v1/chat/completions',headers=auth,json={**body,'stream':False,'model':'bad'}).status_code==400


def test_hashed_secret(context):
    _client, _admin, auth, kid=context
    with gateway.connect() as db:
        row=db.execute('SELECT secret_hash FROM keys WHERE id=?',(kid,)).fetchone()
        assert row['secret_hash'] not in auth['Authorization']
        assert auth['Authorization'].split()[1] not in str(db.execute('SELECT * FROM keys').fetchone().keys())


def make_fake_cli(tmp_path):
    binary = tmp_path/'fake-claude'
    binary.write_text('''#!/usr/bin/env python3
import json,os,sys
if sys.argv[1:] == ['auth', 'status']:
    print(json.dumps({'loggedIn':os.environ.get('MOCK_LOGGED_IN')=='1',
                      'authMethod':os.environ.get('MOCK_AUTH_METHOD','none')}))
    sys.exit(0)
prompt=sys.stdin.read()
assert 'USER:' in prompt and 'Hello CLI' in prompt
assert '--bare' in sys.argv and '--tools' in sys.argv
assert sys.argv[sys.argv.index('--tools')+1] == ''
assert '--disallowedTools' in sys.argv
assert sys.argv[sys.argv.index('--model')+1] == 'haiku'
assert os.environ.get('ANTHROPIC_API_KEY') is None, 'API key was forwarded!'
assert os.environ.get('ANTHROPIC_BASE_URL') is None
assert os.environ.get('ANTHROPIC_AUTH_TOKEN') is None
assert os.environ.get('CLAUDE_CODE_OAUTH_TOKEN') is None
print(json.dumps({'result':'Hello from CLI','usage':{'input_tokens':8,'output_tokens':4}}))
''')
    binary.chmod(0o700)
    return binary


def test_cli_subscription_without_anthropic_api_key(context,monkeypatch,tmp_path):
    client,admin,auth,_kid=context
    mock_cli=make_fake_cli(tmp_path)
    monkeypatch.setenv('CLAUDE_BIN',str(mock_cli))
    monkeypatch.setenv('MOCK_LOGGED_IN','1')
    monkeypatch.setenv('MOCK_AUTH_METHOD','claude.ai')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-must-not-be-forwarded')
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://example.invalid')
    monkeypatch.setenv('ANTHROPIC_AUTH_TOKEN','must-not-be-forwarded')
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN','must-not-be-forwarded')
    assert client.get('/admin/overview',headers=admin).json()['configured'] is True
    r=client.post('/v1/chat/completions',headers=auth,json={'model':'haiku',
                  'messages':[{'role':'user','content':'Hello CLI'}]})
    assert r.status_code == 200, r.text
    assert r.json()['choices'][0]['message']['content']=='Hello from CLI'
    assert r.json()['usage']['total_tokens']==12


def test_prevents_api_key_auth_as_subscription(context,monkeypatch,tmp_path):
    client,admin,auth,_kid=context
    monkeypatch.setenv('CLAUDE_BIN', str(make_fake_cli(tmp_path)))
    monkeypatch.setenv('MOCK_LOGGED_IN','1')
    monkeypatch.setenv('MOCK_AUTH_METHOD','api_key')
    assert client.get('/admin/overview',headers=admin).json()['configured'] is False
    r=client.post('/v1/chat/completions',headers=auth,json={
        'messages':[{'role':'user','content':'Hello CLI'}]})
    assert r.status_code==503
    assert 'subscription' in r.json()['detail']


def test_cli_missing_returns_diagnostic(context, monkeypatch):
    client, admin, auth, _kid=context
    monkeypatch.setenv('CLAUDE_BIN','/does/not/exist')
    assert client.get('/admin/overview',headers=admin).json()['configured'] is False
    r=client.post('/v1/messages',headers=auth,json={
        'messages':[{'role':'user','content':'Hello'}]})
    assert r.status_code==503


def test_direct_api_only_when_explicitly_selected(context,monkeypatch):
    client, admin, auth, _kid=context
    monkeypatch.setenv('GATEWAY_BACKEND','api')
    assert client.get('/admin/overview',headers=admin).json()['configured'] is False
    r=client.post('/v1/chat/completions',headers=auth,json={'messages':[{'role':'user','content':'Hi'}]})
    assert r.status_code==503
    assert 'ANTHROPIC_API_KEY' in r.json()['detail']


def test_cli_only_needs_model_alias(context):
    assert gateway.check_model('sonnet')=='sonnet'
    assert gateway.check_model('opus')=='opus'
    assert gateway.check_model('claude-haiku-5-5')=='haiku'


def test_dashboard_javascript_parses(tmp_path):
    """Catch fatal browser-wide syntax errors like a missing event-handler brace."""
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is not available')
    html = (Path(__file__).resolve().parent.parent / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert '<script>' in html and '</script>' in html
    script = html.split('<script>', 1)[1].split('</script>', 1)[0]
    js_file = tmp_path / 'dashboard.js'
    js_file.write_text(script, encoding='utf-8')
    result = subprocess.run([node, '--check', str(js_file)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

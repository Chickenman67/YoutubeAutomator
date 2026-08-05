import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import pytest
from google.oauth2.credentials import Credentials
from upload import auth as auth_module
from upload.auth import (
    AuthError, DEFAULT_SCOPES, build_client, get_credentials,
    load_credentials, run_auth_flow, save_credentials,
)


def token_json(refresh="refresh-1"):
    return {
        "client_id": "cid",
        "client_secret": "csecret",
        "refresh_token": refresh,
        "token": "tok",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def make_credentials():
    return Credentials(
        token="tok", refresh_token="refresh-1", client_id="cid",
        client_secret="csecret", token_uri="https://oauth2.googleapis.com/token",
    )


def test_load_credentials_reads_stored_refresh_token(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_json()), encoding="utf-8")
    creds = load_credentials(str(path))
    assert isinstance(creds, Credentials)
    assert creds.refresh_token == "refresh-1"
    assert set(creds.scopes) == set(DEFAULT_SCOPES)


def test_load_credentials_raises_when_missing(tmp_path):
    with pytest.raises(AuthError):
        load_credentials(str(tmp_path / "nope.json"))


def test_load_credentials_raises_without_refresh_token(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_json(refresh=None)), encoding="utf-8")
    with pytest.raises(AuthError):
        load_credentials(str(path))


def test_save_credentials_writes_token_file(tmp_path):
    path = save_credentials(make_credentials(), str(tmp_path / "nested" / "token.json"))
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "refresh-1"


def test_get_credentials_returns_stored_when_token_exists(tmp_path):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(token_json()), encoding="utf-8")
    creds = get_credentials(str(path), "cid", "csecret")
    assert creds.refresh_token == "refresh-1"


def test_get_credentials_runs_flow_when_no_token(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    ran = {}

    def fake_run(token_path_arg, client_id, client_secret, scopes=None):
        ran["token_path"] = token_path_arg
        ran["client_id"] = client_id
        return make_credentials()

    monkeypatch.setattr(auth_module, "run_auth_flow", fake_run)
    creds = get_credentials(str(token_path), "cid", "csecret")
    assert creds.refresh_token == "refresh-1"
    assert ran["token_path"] == str(token_path)
    assert ran["client_id"] == "cid"


def test_run_auth_flow_requires_client_credentials(tmp_path):
    with pytest.raises(AuthError):
        run_auth_flow(str(tmp_path / "token.json"), "", "")


def test_run_auth_flow_runs_local_server_and_saves(tmp_path, monkeypatch):
    token_path = tmp_path / "token.json"
    captured = {}

    class FakeFlow:
        def run_local_server(self, prompt=None):
            captured["prompt"] = prompt
            return make_credentials()

    def fake_from_client_config(cls, client_config, scopes=None):
        captured["config"] = client_config
        captured["scopes"] = scopes
        return FakeFlow()

    monkeypatch.setattr(
        auth_module.InstalledAppFlow,
        "from_client_config",
        classmethod(fake_from_client_config),
    )
    creds = run_auth_flow(str(token_path), "cid", "csecret")
    assert creds.refresh_token == "refresh-1"
    assert captured["prompt"] == "consent"
    assert captured["config"]["installed"]["client_id"] == "cid"
    assert token_path.is_file()


def test_build_client_creates_youtube_v3():
    captured = {}
    creds = make_credentials()

    def fake_builder(name, version, credentials=None):
        captured["name"] = name
        captured["version"] = version
        captured["credentials"] = credentials
        return "service"

    assert build_client(creds, builder=fake_builder) == "service"
    assert captured == {"name": "youtube", "version": "v3", "credentials": creds}

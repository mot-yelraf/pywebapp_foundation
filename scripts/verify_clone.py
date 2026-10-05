"""Verify adapting a clean source copy without changing foundation modules.

The current working source may be uncommitted, so export it instead of relying on
git HEAD. Dependencies come from the invoking development interpreter.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXAMPLE = '''"""A replacement application assembled entirely through extension points."""
import asyncio
from pathlib import Path
from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.services.echo import transform
from pwaf_foundation.adapters import FunctionAdapter
from pwaf_foundation.database import Migration
from pwaf_foundation.jobs import JobDefinition
from pwaf_foundation.settings import FoundationSettings
from pwaf_foundation.ui import UIConfig, NavigationItem, SettingsPane, render_page

class Settings(FoundationSettings):
    app_name: str = 'Notebook Lab'
    prefix: str = 'Note'

class Input(BaseModel):
    text: str

def jobs(database):
    def service(parameters, context):
        context.checkpoint()
        return {'text': transform(parameters['text'])}
    async def save(job_id, result):
        def write():
            with database.transaction() as connection:
                connection.execute('INSERT INTO notes VALUES (?, ?)', (job_id, result['text']))
        await asyncio.to_thread(write)
    return {'echo': JobDefinition(Input, FunctionAdapter(service), save=save)}

def example_options():
    router = APIRouter()
    @router.get('/notes')
    async def notes(request: Request):
        return await render_page(request, 'notes.html')
    here = Path(__file__).parent
    return dict(settings_schema=Settings, routers=[router], job_factory=jobs,
        migrations={'notes': [Migration(1, (
            'CREATE TABLE notes (id TEXT PRIMARY KEY, text TEXT)',))]},
        ui=UIConfig(template_dir=here/'templates', navigation=(NavigationItem('Notes', '/notes'),),
                    settings_panes=(SettingsPane('notes', 'Notes', ('prefix',)),)))
'''
CHECK = """
import json, subprocess, sys, time
from pathlib import Path
from fastapi.testclient import TestClient
import pwaf_foundation
from app.app import create_example_app
from pwaf_foundation.config import RuntimeConfig
from scripts.verify_clone import assert_clone_import
assert_clone_import(pwaf_foundation.__file__, Path.cwd())
application = create_example_app(RuntimeConfig(data_dir=Path('data')))
with TestClient(application, base_url='http://127.0.0.1:8191') as client:
    page = client.get('/notes')
    assert page.status_code == 200 and 'Notebook Lab' in page.text and 'Notes' in page.text
    token = client.get('/api/csrf').json()['csrf_token']
    headers = {'Origin':'http://127.0.0.1:8191','X-CSRF-Token':token,'Idempotency-Key':'clone'}
    response=client.patch('/api/settings/panes/notes',json={'prefix':'Saved'},headers=headers)
    assert response.status_code == 200
    assert 'Saved' in client.get('/notes').text
    payload={'operation':'echo','parameters':{'text':'hello'}}
    job = client.post('/api/jobs',json=payload,headers=headers).json()
    for _ in range(200):
        record = client.get(job['status_url']).json()
        if record['status'] in ('succeeded','failed'): break
        time.sleep(.01)
    assert record['status'] == 'succeeded', record
    assert record['result']['text'] == 'HELLO'
    with client.app.state.database.transaction(read_only=True) as connection:
        assert connection.execute('SELECT text FROM notes').fetchone() == ('HELLO',)
    output = subprocess.check_output([sys.executable,'-m','app.cli','hello'],text=True).strip()
    assert output == record['result']['text']
"""


def assert_clone_import(module_file: str, root: Path) -> None:
    """Compare canonical paths so Windows short names and aliases remain equivalent."""
    imported = Path(module_file).resolve()
    clone_root = root.resolve()
    assert imported.is_relative_to(clone_root), (
        f"Foundation imported from {imported}, outside clone {clone_root}"
    )


def hashes(root: Path) -> dict[str, str]:
    """Fingerprint foundation source and assets, excluding interpreter caches."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def main() -> None:
    """Export, replace application features, verify, and compare foundation hashes."""
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="pwaf-clone-") as directory:
        target = Path(directory) / "clean project"
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "__pycache__",
                "build",
                "dist",
                "*.egg-info",
                "data",
                ".coverage*",
                ".pytest_cache",
                ".ruff_cache",
            ),
        )
        before = hashes(target / "pwaf_foundation")
        (target / "app/identity.json").write_text(' {"id": "notebook-lab"}\n')
        (target / "app/example.py").write_text(EXAMPLE)
        (target / "app/services/echo.py").write_text(
            "def transform(text):\n    return text.upper()\n"
        )
        (target / "app/cli.py").write_text(
            "import sys\nfrom app.services.echo import transform\nprint(transform(sys.argv[1]))\n"
        )
        (target / "app/templates/notes.html").write_text(
            "{% extends 'base.html' %}{% block content %}"
            "<h1>{{ settings.prefix }}</h1>{% endblock %}"
        )
        env = {key: value for key, value in os.environ.items() if not key.startswith("PWAF_")}
        env["PYTHONPATH"] = str(target)
        subprocess.run(
            [sys.executable, "-W", "error", "-c", CHECK], cwd=target, env=env, check=True
        )
        assert before == hashes(target / "pwaf_foundation")
    print(
        "Clean-copy adaptation passed: branding, CLI/service, route, pane, table, "
        "and job; foundation unchanged."
    )


if __name__ == "__main__":
    main()

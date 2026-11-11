"""Real Prefect server, deployment runner and child-process crash/replay tests.

Only provider HTTP is intercepted in a test-only Python startup module. No SDK,
engine, database transaction or domain stage is replaced with a fake.
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest

from nima.__main__ import main
from nima.orchestration.dispatch import dispatch_request
from nima.storage.postgres import migrate
from nima.storage.workflows import RequestStore
from tests.test_collection import QUERY, body


def wait(condition: Callable[[], bool], timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            pytest.fail("Local workflow boundary did not finish within its test budget")
        time.sleep(0.1)


def stop(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


@pytest.fixture
def engine(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, str]]:
    migrate(pg_dsn)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {
        **os.environ,
        "PREFECT_API_URL": f"http://127.0.0.1:{port}/api",
        "PREFECT_HOME": str(tmp_path / "control"),
        "PREFECT_SERVER_EPHEMERAL_ENABLED": "false",
        "PREFECT_SERVER_ANALYTICS_ENABLED": "false",
        "PREFECT_LOGGING_LEVEL": "WARNING",
        "PREFECT_RUNNER_POLL_FREQUENCY": "1",
        "PREFECT_RUNNER_HEARTBEAT_FREQUENCY": "30",
        "NIMA_DATABASE_URL": pg_dsn,
        "NIMA_ARCHIVE_ROOT": str(tmp_path / "raw"),
    }
    environment.pop("PREFECT_API_KEY", None)
    for key, value in environment.items():
        if key.startswith(("NIMA_", "PREFECT_")):
            monkeypatch.setenv(key, value)
    monkeypatch.delenv("PREFECT_API_KEY", raising=False)
    with (tmp_path / "server.log").open("wb") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "prefect",
                "server",
                "start",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

        def healthy() -> bool:
            if server.poll() is not None:
                pytest.fail(
                    "Prefect server exited: " + (tmp_path / "server.log").read_text()[-3000:]
                )
            try:
                return (
                    httpx.get(environment["PREFECT_API_URL"] + "/health", timeout=1).status_code
                    == 200
                )
            except httpx.HTTPError:
                return False

        try:
            wait(healthy)
            yield environment
        finally:
            stop(server)


HOOK = """
import os, signal
from pathlib import Path
import httpx
original_http=httpx.HTTPTransport.handle_request
def http(self, request):
    if request.url.host=='cerpp.eprocurement.gov.gr':
        with open(os.environ['NIMA_TEST_CALLS'],'a') as log: log.write('provider\\n')
        return httpx.Response(200,content=Path(os.environ['NIMA_TEST_BODY']).read_bytes(),
                              headers={'content-type':'application/json'},request=request)
    if request.url.host not in ('localhost','127.0.0.1','::1'):
        raise RuntimeError('External network blocked by workflow test')
    return original_http(self,request)
httpx.HTTPTransport.handle_request=http
from nima.orchestration import pipeline
def wrap(original,boundary):
    def call(*args,**kwargs):
        if boundary=='collect' and os.environ.get('NIMA_TEST_BOUNDARY')=='retry':
            ready=Path(os.environ['NIMA_TEST_READY'])
            if not ready.exists():
                ready.write_text('retry')
                from nima.storage.workflows import WorkflowError
                raise WorkflowError('database',True)
        result=original(*args,**kwargs)
        if os.environ.get('NIMA_TEST_BOUNDARY')==boundary:
            ready=Path(os.environ['NIMA_TEST_READY'])
            try:
                with ready.open('x') as output: output.write(str(os.getpid()))
            except FileExistsError: return result
            signal.pause()
        return result
    return call
pipeline.collect_request=wrap(pipeline.collect_request,'collect')
pipeline.project_request=wrap(pipeline.project_request,'project')
"""


def runner(
    environment: dict[str, str], root: Path, *, boundary: str = ""
) -> subprocess.Popen[bytes]:
    hooks = root / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "sitecustomize.py").write_text(HOOK)
    (root / "source.json").write_bytes(body(total=1))
    environment = {
        **environment,
        "PYTHONPATH": str(hooks),
        "NIMA_TEST_BODY": str(root / "source.json"),
        "NIMA_TEST_CALLS": str(root / "calls"),
        "NIMA_TEST_READY": str(root / "ready"),
        "NIMA_TEST_BOUNDARY": boundary,
    }
    with (root / "runner.log").open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "nima.orchestration.runner"],
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    def deployed() -> bool:
        if process.poll() is not None:
            pytest.fail("Runner exited: " + (root / "runner.log").read_text()[-3000:])
        response = httpx.get(
            environment["PREFECT_API_URL"] + "/deployments/name/nima-kimdis/local", timeout=2
        )
        return response.status_code == 200

    try:
        wait(deployed)
    except BaseException:
        stop(process)
        raise
    return process


@pytest.mark.parametrize("boundary", ["", "retry"])
def test_real_server_dispatch_and_runner_complete_once(
    engine: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str], boundary: str
) -> None:
    requests = RequestStore(engine["NIMA_DATABASE_URL"])
    request = uuid4()
    worker = runner(engine, tmp_path, boundary=boundary)
    try:
        deployed = httpx.get(
            engine["PREFECT_API_URL"] + "/deployments/name/nima-kimdis/local"
        ).json()
        assert deployed["entrypoint"] == "nima.orchestration.flows.kimdis_flow"
        assert (
            main(
                [
                    "workflows",
                    "submit",
                    "kimdis",
                    "--request-id",
                    str(request),
                    "--from-date",
                    "2026-11-06",
                    "--to-date",
                    "2026-11-06",
                    "--buyer-id",
                    "00123",
                ]
            )
            == 0
        )
        sent = json.loads(capsys.readouterr().out)
        assert sent["dispatch_status"] == "accepted"
        wait(lambda: requests.show(request)["status"] == "complete")
        assert (tmp_path / "calls").read_text().splitlines() == ["provider"]
        assert requests.show(request)["executions"] == 1
        assert asyncio.run(dispatch_request(request))["status"] == "complete"
        assert requests.show(request)["dispatches"] == 1

        async def duplicate() -> UUID:
            from prefect.client.orchestration import PrefectClient

            async with PrefectClient(api=engine["PREFECT_API_URL"], api_key=None) as client:
                run = await client.create_flow_run_from_deployment(
                    UUID(deployed["id"]),
                    parameters={"request_id": str(request)},
                    idempotency_key=uuid4().hex,
                )
                return run.id

        duplicate_id = asyncio.run(duplicate())
        wait(
            lambda: (
                httpx.get(engine["PREFECT_API_URL"] + "/flow_runs/" + str(duplicate_id)).json()[
                    "state_type"
                ]
                == "COMPLETED"
            )
        )
        assert (tmp_path / "calls").read_text().splitlines() == ["provider"]
        assert requests.show(request)["executions"] == 1
    finally:
        stop(worker)


DISPATCH_WORKER = """
import asyncio,os,signal
from pathlib import Path
from uuid import UUID
from nima.storage.workflows import RequestStore
from nima.orchestration.dispatch import dispatch_request
def pause():
    Path(os.environ['NIMA_DISPATCH_READY']).write_text('ready')
    signal.pause()
original=RequestStore.begin_dispatch
def begin(self,*args,**kwargs):
    result=original(self,*args,**kwargs)
    if os.environ['NIMA_DISPATCH_BOUNDARY']=='before': pause()
    return result
RequestStore.begin_dispatch=begin
finish=RequestStore.finish_dispatch
def end(self,*args,**kwargs):
    if os.environ['NIMA_DISPATCH_BOUNDARY']=='after': pause()
    return finish(self,*args,**kwargs)
RequestStore.finish_dispatch=end
asyncio.run(dispatch_request(UUID(os.environ['NIMA_DISPATCH_REQUEST'])))
"""


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_dispatch_kill_keeps_pending_outcome_and_safe_redispatch(
    engine: dict[str, str], tmp_path: Path, boundary: str
) -> None:
    async def register() -> None:
        from prefect.client.orchestration import PrefectClient

        async with PrefectClient(api=engine["PREFECT_API_URL"], api_key=None) as client:
            flow = await client.create_flow_from_name("nima-kimdis")
            await client.create_deployment(
                flow, name="local", entrypoint="nima.orchestration.flows.kimdis_flow"
            )

    asyncio.run(register())
    store = RequestStore(engine["NIMA_DATABASE_URL"])
    request = uuid4()
    store.submit(request, QUERY, Path(engine["NIMA_ARCHIVE_ROOT"]))
    ready = tmp_path / "dispatch-ready"
    environment = {
        **engine,
        "NIMA_DISPATCH_BOUNDARY": boundary,
        "NIMA_DISPATCH_READY": str(ready),
        "NIMA_DISPATCH_REQUEST": str(request),
    }
    with (tmp_path / "dispatch.log").open("wb") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", DISPATCH_WORKER],
            env=environment,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            wait(ready.exists)
            process.kill()
            process.wait(timeout=5)
            value = store.show(request)
            assert value["status"] == "queued" and value["unknown_dispatches"] == 1
            assert value["engine_run_id"] is None and value["attempts"] == 0
            runs = httpx.post(engine["PREFECT_API_URL"] + "/flow_runs/filter", json={}).json()
            assert len(runs) == int(boundary == "after")
            assert asyncio.run(dispatch_request(request))["dispatch_status"] == "accepted"
            assert store.show(request)["dispatches"] == 2
            assert not Path(engine["NIMA_ARCHIVE_ROOT"]).exists()
        finally:
            stop(process)


@pytest.mark.parametrize("boundary", ["collect", "project"])
def test_real_flow_sigkill_and_redispatch_reuse_sql_progress(
    engine: dict[str, str], tmp_path: Path, boundary: str
) -> None:
    dsn = engine["NIMA_DATABASE_URL"]
    requests = RequestStore(dsn)
    request = uuid4()
    requests.submit(request, QUERY, Path(engine["NIMA_ARCHIVE_ROOT"]))
    worker = runner(engine, tmp_path, boundary=boundary)
    try:
        first = asyncio.run(dispatch_request(request))
        ready = tmp_path / "ready"
        wait(lambda: ready.exists() and ready.read_text().isdigit())
        run = requests.show(request)["run_id"]
        assert requests.show(request)["status"] != "complete"
        os.kill(int(ready.read_text()), signal.SIGKILL)
        wait(
            lambda: (
                httpx.get(
                    engine["PREFECT_API_URL"] + "/flow_runs/" + str(first["engine_run_id"])
                ).json()["state_type"]
                in {"CRASHED", "FAILED"}
            )
        )
        with psycopg.connect(dsn) as connection:
            assert connection.execute("SELECT count(*) FROM nima.observations").fetchone() == (1,)
        stop(worker)
        worker = runner(engine, tmp_path, boundary=boundary)
        second = asyncio.run(dispatch_request(request))
        assert first["engine_run_id"] != second["engine_run_id"]
        wait(lambda: requests.show(request)["status"] == "complete")
        assert requests.show(request)["run_id"] == run
        assert (tmp_path / "calls").read_text().splitlines() == ["provider"]
        assert requests.show(request)["executions"] == 1
        with psycopg.connect(dsn) as connection:
            assert connection.execute(
                "SELECT count(*) FROM nima.projection_receipts"
            ).fetchone() == (1,)
    finally:
        stop(worker)

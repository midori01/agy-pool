import contextlib
import email.message
import http.client
import http.server
import importlib.machinery
import importlib.util
import json
import multiprocessing
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bin", "agy-pool")
loader = importlib.machinery.SourceFileLoader("agy_pool", SCRIPT)
spec = importlib.util.spec_from_loader(loader.name, loader)
agy_pool = importlib.util.module_from_spec(spec)
loader.exec_module(agy_pool)


def account(account_id, token=None):
    return {
        "id": account_id,
        "email": f"{account_id}@example.test",
        "refresh_token": f"refresh-{account_id}",
        "access_token": token or f"token-{account_id}",
        "token_expiry": time.time() + 3600,
        "request_count": 0,
        "error_count": 0,
        "last_quota": {"remaining_fraction": 1.0},
    }


class Scenario:
    def __init__(self, actions):
        self.actions = {key: list(value) for key, value in actions.items()}
        self.calls = []
        self.lock = threading.Lock()

    def take(self, token, request):
        with self.lock:
            self.calls.append((token, request.path, dict(request.headers)))
            choices = self.actions.get(token, self.actions.get("*", []))
            if not choices:
                return (200, b"ok", {})
            return choices.pop(0)


def upstream_handler(scenario):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.respond()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.body = self.rfile.read(length)
            self.respond()

        def respond(self):
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else authorization
            action = scenario.take(token, self)
            if callable(action):
                action(self)
                return
            status, body, headers = action
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    return Handler


class AgyPoolTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home_patch = mock.patch.dict(os.environ, {"HOME": self.temp.name})
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        gemini = os.path.join(self.temp.name, ".gemini")
        agy_pool.GEMINI_DIR = gemini
        agy_pool.POOL_CONFIG_FILE = os.path.join(gemini, "agy-pool-accounts.json")
        agy_pool.PID_FILE = os.path.join(gemini, "agy-pool.pid")
        agy_pool.LOG_FILE = os.path.join(gemini, "agy-pool.log")
        agy_pool.AGY_CLI_DIR = os.path.join(gemini, "antigravity-cli")
        agy_pool.AGY_TOKEN_FILE = os.path.join(agy_pool.AGY_CLI_DIR, "antigravity-oauth-token")
        agy_pool.FILE_LOCKS.clear()

    def save_accounts(self, accounts, active="a"):
        agy_pool.save_pool({
            "version": 1,
            "strategy": "max_quota",
            "active_account_id": active,
            "accounts": accounts,
        })

    def start_server(self, handler):
        server = agy_pool.ThreadedHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def start_proxy(self, scenario):
        upstream = self.start_server(upstream_handler(scenario))
        host, port = upstream.server_address
        agy_pool.BACKEND_HOST = f"{host}:{port}"
        agy_pool.BACKEND_URL_BASE = f"http://{host}:{port}"
        proxy = self.start_server(agy_pool.SmartProxyHandler)
        self.assertEqual(proxy.server_address[0], "127.0.0.1")
        return proxy

    def request(self, proxy, path="/v1/test", body=b"{}", headers=None):
        conn = http.client.HTTPConnection(*proxy.server_address, timeout=3)
        conn.request("POST", path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        result = (response.status, data, dict(response.getheaders()))
        conn.close()
        return result

    def test_threaded_request_count_transaction_has_no_lost_updates(self):
        self.save_accounts([account("a")])

        def increment():
            def update(pool):
                pool["accounts"][0]["request_count"] += 1
            agy_pool.pool_transaction(update)

        threads = [threading.Thread(target=increment) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(agy_pool.load_pool()["accounts"][0]["request_count"], 20)

    def test_processes_update_different_accounts_without_overwrite(self):
        self.save_accounts([account("a"), account("b")])
        context = multiprocessing.get_context("fork")

        def worker(account_id):
            for _ in range(5):
                def update(pool):
                    next(a for a in pool["accounts"] if a["id"] == account_id)["request_count"] += 1
                agy_pool.pool_transaction(update)

        processes = [context.Process(target=worker, args=(account_id,))
                     for account_id in ("a", "b")]
        for process in processes:
            process.start()
        for process in processes:
            process.join(20)
            self.assertEqual(process.exitcode, 0)
        counts = {a["id"]: a["request_count"] for a in agy_pool.load_pool()["accounts"]}
        self.assertEqual(counts, {"a": 5, "b": 5})

    def test_quota_refresh_and_request_handler_merge_fields(self):
        acc = account("a")
        self.save_accounts([acc])

        def quota_update(snapshot):
            time.sleep(0.02)
            snapshot["last_quota"] = {"remaining_fraction": 0.4, "updated_at": 123}
            return snapshot["last_quota"]

        with mock.patch.object(agy_pool, "query_quota", quota_update):
            refresher = threading.Thread(target=agy_pool._safe_quota, args=(dict(acc),))
            refresher.start()
            for _ in range(25):
                agy_pool.SmartProxyHandler._record_success(None, acc)
            refresher.join()
        stored = agy_pool.load_pool()["accounts"][0]
        self.assertEqual(stored["request_count"], 25)
        self.assertEqual(stored["last_quota"]["remaining_fraction"], 0.4)

    def test_simultaneous_token_refresh_is_single_flight(self):
        acc = account("a")
        acc["token_expiry"] = 0
        self.save_accounts([acc])
        calls = []
        call_lock = threading.Lock()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"access_token":"fresh","expires_in":3600}'

        def urlopen(*args, **kwargs):
            with call_lock:
                calls.append(1)
            time.sleep(0.03)
            return Response()

        snapshots = [dict(acc) for _ in range(12)]
        with mock.patch.object(agy_pool.urllib.request, "urlopen", urlopen):
            threads = [threading.Thread(target=agy_pool.refresh_token, args=(item,))
                       for item in snapshots]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(calls), 1)
        self.assertEqual(agy_pool.load_pool()["accounts"][0]["access_token"], "fresh")

    def test_process_token_refresh_is_single_flight(self):
        acc = account("a")
        acc["token_expiry"] = 0
        self.save_accounts([acc])
        context = multiprocessing.get_context("fork")
        calls = context.Value("i", 0)

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b'{"access_token":"fresh-process","expires_in":3600}'

        def urlopen(*args, **kwargs):
            with calls.get_lock():
                calls.value += 1
            time.sleep(0.03)
            return Response()

        def refresh():
            agy_pool.refresh_token(dict(acc))

        with mock.patch.object(agy_pool.urllib.request, "urlopen", urlopen):
            processes = [context.Process(target=refresh) for _ in range(4)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
        self.assertEqual(calls.value, 1)

    def test_failed_quota_refresh_preserves_cached_quota(self):
        acc = account("a")
        acc["last_quota"] = {"remaining_fraction": 0.25, "updated_at": 10}
        self.save_accounts([acc])
        with mock.patch.object(agy_pool.urllib.request, "urlopen",
                               side_effect=OSError("upstream unavailable")):
            self.assertFalse(agy_pool._safe_quota(dict(acc)))
        self.assertEqual(agy_pool.load_pool()["accounts"][0]["last_quota"],
                         {"remaining_fraction": 0.25, "updated_at": 10})

        class EmptyResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b"{}"

        with mock.patch.object(agy_pool.urllib.request, "urlopen", return_value=EmptyResponse()):
            self.assertFalse(agy_pool._safe_quota(dict(acc)))
        self.assertEqual(agy_pool.load_pool()["accounts"][0]["last_quota"],
                         {"remaining_fraction": 0.25, "updated_at": 10})

    def test_429_before_commit_fails_over(self):
        self.save_accounts([account("a"), account("b")])
        agy_pool.write_agy_token_file(account("a"))
        with open(agy_pool.AGY_TOKEN_FILE, "rb") as token_file:
            compatibility_token = token_file.read()
        scenario = Scenario({
            "token-a": [(429, b'{"error":{"status":"RESOURCE_EXHAUSTED"}}', {})],
            "token-b": [(200, b"from-b", {})],
        })
        proxy = self.start_proxy(scenario)
        status, body, _ = self.request(proxy, "/v1internal:streamGenerateContent")
        self.assertEqual((status, body), (200, b"from-b"))
        self.assertEqual([call[0] for call in scenario.calls], ["token-a", "token-b"])
        with open(agy_pool.AGY_TOKEN_FILE, "rb") as token_file:
            self.assertEqual(token_file.read(), compatibility_token)

    def test_quota_403_fails_over_but_permission_403_does_not(self):
        self.save_accounts([account("a"), account("b")])
        quota = Scenario({
            "token-a": [(403, b'{"error":{"status":"RESOURCE_EXHAUSTED"}}', {})],
            "token-b": [(200, b"from-b", {})],
        })
        proxy = self.start_proxy(quota)
        self.assertEqual(self.request(proxy)[0:2], (200, b"from-b"))

        self.save_accounts([account("a"), account("b")])
        denied = Scenario({
            "token-a": [(403, b'{"error":{"status":"PERMISSION_DENIED"}}', {})],
            "token-b": [(200, b"wrong-retry", {})],
        })
        proxy = self.start_proxy(denied)
        self.assertEqual(self.request(proxy)[0:2], (403, b'{"error":{"status":"PERMISSION_DENIED"}}'))
        self.assertEqual([call[0] for call in denied.calls], ["token-a"])

    def test_validation_required_fails_over_and_persists_status(self):
        self.save_accounts([account("a"), account("b")])
        val_error = {
            "error": {
                "code": 403,
                "message": "Verify your account to continue.",
                "status": "PERMISSION_DENIED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                        "reason": "VALIDATION_REQUIRED",
                        "metadata": {
                            "validation_url": "https://accounts.google.com/signin/continue?foo=bar"
                        }
                    }
                ]
            }
        }
        val_body = json.dumps(val_error).encode()
        scenario = Scenario({
            "token-a": [(403, val_body, {})],
            "token-b": [(200, b"success-from-b", {})],
        })
        proxy = self.start_proxy(scenario)
        status, body, _ = self.request(proxy, "/v1internal:streamGenerateContent")
        self.assertEqual((status, body), (200, b"success-from-b"))
        self.assertEqual([call[0] for call in scenario.calls], ["token-a", "token-b"])

        pool = agy_pool.load_pool()
        acc_a = next(a for a in pool["accounts"] if a["id"] == "a")
        self.assertEqual(acc_a.get("status"), "validation_required")
        self.assertEqual(acc_a.get("validation_url"), "https://accounts.google.com/signin/continue?foo=bar")
        self.assertEqual(acc_a.get("last_quota", {}).get("remaining_fraction"), 0.0)

    def test_started_sse_failure_is_not_replayed(self):
        self.save_accounts([account("a"), account("b")])

        def broken_stream(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()
            handler.wfile.write(b"B\r\ndata: one\n\n\r\nZZ\r\n")
            handler.wfile.flush()
            handler.close_connection = True

        scenario = Scenario({"token-a": [broken_stream], "token-b": [(200, b"replayed", {})]})
        proxy = self.start_proxy(scenario)
        conn = http.client.HTTPConnection(*proxy.server_address, timeout=3)
        conn.request("POST", "/v1internal:streamGenerateContent", body=b"{}")
        response = conn.getresponse()
        with self.assertRaises(http.client.IncompleteRead) as error:
            response.read()
        self.assertIn(b"data: one", error.exception.partial)
        conn.close()
        self.assertEqual([call[0] for call in scenario.calls], ["token-a"])

    def test_client_disconnect_closes_upstream_response(self):
        self.save_accounts([account("a")])
        closed = threading.Event()

        class Response:
            status = 200
            headers = email.message.Message()
            headers["Content-Type"] = "text/event-stream"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                closed.set()

            def read1(self, size):
                return b"x" * 262144

        proxy = self.start_server(agy_pool.SmartProxyHandler)
        with mock.patch.object(agy_pool.urllib.request, "urlopen", return_value=Response()):
            client = socket.create_connection(proxy.server_address, timeout=2)
            client.sendall(b"POST /stream HTTP/1.1\r\nHost: local\r\nContent-Length: 2\r\n\r\n{}")
            client.recv(1024)
            client.close()
            self.assertTrue(closed.wait(3))

    def test_clean_upstream_eof_finishes_chunked_stream(self):
        self.save_accounts([account("a")])
        scenario = Scenario({"token-a": [(200, b"data: done\n\n", {"Content-Type": "text/event-stream"})]})
        proxy = self.start_proxy(scenario)
        self.assertEqual(self.request(proxy, "/stream")[0:2], (200, b"data: done\n\n"))

    def test_malformed_upstream_chunking_returns_502_before_commit(self):
        self.save_accounts([account("a")])

        def malformed(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()
            handler.wfile.write(b"5\r\nabc")
            handler.wfile.flush()
            handler.close_connection = True

        proxy = self.start_proxy(Scenario({"token-a": [malformed]}))
        self.assertEqual(self.request(proxy)[0], 502)

    def test_upstream_timeout_returns_504_without_replay(self):
        self.save_accounts([account("a"), account("b")])
        proxy = self.start_server(agy_pool.SmartProxyHandler)
        calls = []

        def timeout(*args, **kwargs):
            calls.append(1)
            raise socket.timeout("timed out")

        with mock.patch.object(agy_pool.urllib.request, "urlopen", timeout):
            self.assertEqual(self.request(proxy)[0], 504)
        self.assertEqual(len(calls), 1)

    def test_malformed_client_chunking_is_rejected(self):
        self.save_accounts([account("a")])
        scenario = Scenario({"token-a": [(200, b"must-not-run", {})]})
        proxy = self.start_proxy(scenario)
        client = socket.create_connection(proxy.server_address, timeout=2)
        client.sendall(b"POST /v1/test HTTP/1.1\r\nHost: local\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\nZ\r\n")
        client.shutdown(socket.SHUT_WR)
        response = b""
        while True:
            part = client.recv(4096)
            if not part:
                break
            response += part
        client.close()
        self.assertIn(b" 400 ", response.split(b"\r\n", 1)[0])
        self.assertEqual(scenario.calls, [])

    def test_valid_chunked_request_is_reassembled(self):
        self.save_accounts([account("a")])
        received = []

        def capture(handler):
            received.append(handler.body)
            handler.send_response(200)
            handler.send_header("Content-Length", "2")
            handler.end_headers()
            handler.wfile.write(b"ok")

        proxy = self.start_proxy(Scenario({"token-a": [capture]}))
        client = socket.create_connection(proxy.server_address, timeout=2)
        client.sendall(b"POST /v1/test HTTP/1.1\r\nHost: local\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n")
        response = b""
        while True:
            part = client.recv(4096)
            if not part:
                break
            response += part
        client.close()
        self.assertIn(b" 200 ", response.split(b"\r\n", 1)[0])
        self.assertEqual(received, [b"abcde"])

    def test_hop_by_hop_headers_removed_and_content_encoding_preserved(self):
        self.save_accounts([account("a")])
        scenario = Scenario({"token-a": [(200, b"encoded", {"Content-Encoding": "test"})]})
        proxy = self.start_proxy(scenario)
        status, _, headers = self.request(proxy, headers={
            "Connection": "X-Remove",
            "X-Remove": "secret",
            "Proxy-Connection": "keep-alive",
        })
        self.assertEqual(status, 200)
        upstream_headers = scenario.calls[0][2]
        self.assertNotIn("X-Remove", upstream_headers)
        self.assertNotIn("Proxy-Connection", upstream_headers)
        self.assertEqual(headers["Content-Encoding"], "test")

    def test_two_concurrent_sessions_update_state_without_corrupting_token_file(self):
        self.save_accounts([account("a")])
        agy_pool.write_agy_token_file(account("a"))
        with open(agy_pool.AGY_TOKEN_FILE, "rb") as token_file:
            before = token_file.read()
        scenario = Scenario({"token-a": [(200, b"one", {}), (200, b"two", {})]})
        proxy = self.start_proxy(scenario)
        results = []

        def session():
            results.append(self.request(proxy, "/v1internal:generateContent")[0])

        threads = [threading.Thread(target=session) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(results, [200, 200])
        self.assertEqual(agy_pool.load_pool()["accounts"][0]["request_count"], 2)
        with open(agy_pool.AGY_TOKEN_FILE, "rb") as token_file:
            self.assertEqual(token_file.read(), before)
        self.assertEqual(os.stat(agy_pool.AGY_TOKEN_FILE).st_mode & 0o777, 0o600)

    def test_active_switch_does_not_change_in_flight_account(self):
        self.save_accounts([account("a"), account("b")])
        started = threading.Event()
        release = threading.Event()

        def blocked_stream(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.send_header("Content-Length", "12")
            handler.end_headers()
            started.set()
            release.wait(2)
            handler.wfile.write(b"data: done\n\n")

        scenario = Scenario({"token-a": [blocked_stream], "token-b": [(200, b"new-active", {})]})
        proxy = self.start_proxy(scenario)
        result = []
        running = threading.Thread(target=lambda: result.append(self.request(proxy, "/stream")[1]))
        running.start()
        self.assertTrue(started.wait(2))
        agy_pool.pool_transaction(lambda pool: pool.update(active_account_id="b"))
        release.set()
        running.join(3)
        self.assertEqual(result, [b"data: done\n\n"])
        self.assertEqual(self.request(proxy, "/metadata")[1], b"new-active")
        self.assertEqual([call[0] for call in scenario.calls], ["token-a", "token-b"])

    def test_state_permissions_and_failed_transaction_preserve_state(self):
        self.save_accounts([account("a")])
        self.assertEqual(os.stat(agy_pool.POOL_CONFIG_FILE).st_mode & 0o777, 0o600)
        with open(agy_pool.POOL_CONFIG_FILE, "rb") as state:
            before = state.read()
        with self.assertRaises(RuntimeError):
            agy_pool.pool_transaction(lambda pool: (_ for _ in ()).throw(RuntimeError("crash")))
        with open(agy_pool.POOL_CONFIG_FILE, "rb") as state:
            self.assertEqual(state.read(), before)

    def test_corrupt_state_is_not_replaced(self):
        agy_pool.ensure_dirs()
        with open(agy_pool.POOL_CONFIG_FILE, "wb") as state:
            state.write(b"{broken")
        with self.assertRaises(json.JSONDecodeError):
            agy_pool.pool_transaction(lambda pool: pool.update(strategy="round_robin"))
        with open(agy_pool.POOL_CONFIG_FILE, "rb") as state:
            self.assertEqual(state.read(), b"{broken")

    def test_daemon_sigterm_closes_listener_and_removes_owned_pid(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        previous_port = agy_pool.DEFAULT_PORT
        agy_pool.DEFAULT_PORT = port
        self.addCleanup(setattr, agy_pool, "DEFAULT_PORT", previous_port)
        process = multiprocessing.get_context("fork").Process(
            target=agy_pool.start_proxy_daemon, args=(True,))
        process.start()
        self.addCleanup(lambda: process.is_alive() and process.terminate())
        for _ in range(50):
            if os.path.exists(agy_pool.PID_FILE):
                break
            time.sleep(0.02)
        self.assertTrue(os.path.exists(agy_pool.PID_FILE))
        process.terminate()
        process.join(5)
        self.assertEqual(process.exitcode, 0)
        self.assertFalse(os.path.exists(agy_pool.PID_FILE))
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)

    def test_conversation_continuation_lookup(self):
        workspace = os.path.join(self.temp.name, "project", "subdir")
        os.makedirs(workspace)
        db_dir = os.path.join(self.temp.name, ".gemini", "antigravity-cli")
        os.makedirs(db_dir, exist_ok=True)
        db = os.path.join(db_dir, "conversation_summaries.db")
        with sqlite3.connect(db) as connection:
            connection.execute("CREATE TABLE conversation_summaries (conversation_id, title, workspace_uris, last_modified_time)")
            connection.execute("INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)",
                               ("old", "Old", json.dumps(["file://" + workspace]), 1))
            connection.execute("INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)",
                               ("new", "New", json.dumps(["file://" + workspace]), 2))
        connection.close()
        self.assertEqual(agy_pool.find_latest_conversation_for_dir(workspace)[0], "new")

    def test_agy_raw_bypasses_proxy_and_preserves_arguments(self):
        native = os.path.join(self.temp.name, "agy-native")
        with open(native, "w", encoding="utf-8") as script:
            script.write('#!/bin/sh\nprintf "%s\\n" "${CLOUD_CODE_URL-unset}" "$@"\n')
        os.chmod(native, 0o700)
        env = dict(os.environ, AGY_BIN=native, CLOUD_CODE_URL="http://127.0.0.1:8899")
        result = subprocess.run(["bash", os.path.join(ROOT, "bin", "agy-raw"), "--model", "x"],
                                env=env, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ["unset", "--model", "x"])

    def test_do_verify_opens_browser_and_clears_status(self):
        acc = account("a")
        acc["status"] = "validation_required"
        acc["validation_url"] = "https://accounts.google.com/verify-test"
        self.save_accounts([acc])

        def fake_query(account_data):
            account_data.pop("status", None)
            account_data.pop("validation_url", None)
            agy_pool._persist_account_fields(account_data, ("status", "validation_url"))
            return {"remaining_fraction": 1.0}

        with mock.patch.object(agy_pool, "query_quota", fake_query):
            res = agy_pool.do_verify("a")
            self.assertTrue(res)
            pool = agy_pool.load_pool()
            self.assertIsNone(pool["accounts"][0].get("status"))


if __name__ == "__main__":
    unittest.main()

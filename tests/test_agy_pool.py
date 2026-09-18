import base64
import contextlib
import email.message
import errno
import http.client
import http.server
import importlib.machinery
import ssl
import importlib.util
import io
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
import urllib.error
import urllib.parse
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
        self.assertEqual(agy_pool.load_pool()["accounts"][0]["gen_count"], 2)
        with open(agy_pool.AGY_TOKEN_FILE, "rb") as token_file:
            self.assertEqual(token_file.read(), before)
        self.assertEqual(os.stat(agy_pool.AGY_TOKEN_FILE).st_mode & 0o777, 0o600)

    def test_generation_vs_metadata_request_counts(self):
        self.save_accounts([account("a")])
        scenario = Scenario({"token-a": [(200, b"gen", {}), (200, b"meta", {})]})
        proxy = self.start_proxy(scenario)
        self.request(proxy, "/v1internal:generateContent")
        acc = agy_pool.load_pool()["accounts"][0]
        self.assertEqual(acc.get("gen_count"), 1)
        self.assertEqual(acc.get("request_count"), 1)

        self.request(proxy, "/v1internal:fetchUserInfo")
        acc = agy_pool.load_pool()["accounts"][0]
        self.assertEqual(acc.get("gen_count"), 1)
        self.assertEqual(acc.get("request_count"), 2)

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

    def test_rotate_log_if_needed_threshold(self):
        log_path = os.path.join(self.temp.name, "test.log")
        with open(log_path, "wb") as f:
            f.write(b"x" * 1000)

        # Below threshold: no rotation
        rotated = agy_pool.rotate_log_if_needed(log_path, max_bytes=2000, backup_count=1)
        self.assertFalse(rotated)
        self.assertEqual(os.path.getsize(log_path), 1000)
        self.assertFalse(os.path.exists(log_path + ".1"))

        # Above threshold: rotate
        rotated = agy_pool.rotate_log_if_needed(log_path, max_bytes=500, backup_count=1)
        self.assertTrue(rotated)
        self.assertEqual(os.path.getsize(log_path), 0)
        self.assertTrue(os.path.exists(log_path + ".1"))
        self.assertEqual(os.path.getsize(log_path + ".1"), 1000)

    def test_rotate_log_copytruncate_preserves_open_fd(self):
        log_path = os.path.join(self.temp.name, "active.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("first line\n")
            f.flush()

            # Rotate while file is still held open by a process/daemon
            rotated = agy_pool.rotate_log_if_needed(log_path, force=True, backup_count=1)
            self.assertTrue(rotated)

            # Subsequent writes to open fd continue writing to truncated active log
            f.write("second line\n")
            f.flush()

        with open(log_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "second line\n")
        with open(log_path + ".1", "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "first line\n")

    def test_clear_log(self):
        log_path = os.path.join(self.temp.name, "clear.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("active content\n")
        with open(log_path + ".1", "w", encoding="utf-8") as f:
            f.write("backup content\n")

        agy_pool.clear_log(log_path, backup_count=1)
        self.assertEqual(os.path.getsize(log_path), 0)
        self.assertFalse(os.path.exists(log_path + ".1"))

    def test_show_logs_clear_and_rotate_flags(self):
        log_path = os.path.join(self.temp.name, "cli.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("log line 1\nlog line 2\n")

        with mock.patch.object(agy_pool, "LOG_FILE", log_path):
            with mock.patch("sys.stdout") as mock_stdout:
                agy_pool.show_logs(rotate=True)
                self.assertTrue(os.path.exists(log_path + ".1"))
                self.assertEqual(os.path.getsize(log_path), 0)

                agy_pool.show_logs(clear=True)
                self.assertFalse(os.path.exists(log_path + ".1"))

    def test_list_accounts_exhausted_and_hits(self):
        acc1 = account("a")
        acc1["gen_count"] = 42
        acc1["request_count"] = 100
        acc1["last_quota"] = {
            "gemini_5h": {"fraction": 0.8},
            "gemini_weekly": {"fraction": 0.9},
        }

        acc2 = account("b")
        acc2["gen_count"] = 15
        acc2["request_count"] = 30
        acc2["last_quota"] = {
            "gemini_5h": {"fraction": 1.0},
            "gemini_weekly": {"fraction": 0.0},
        }

        acc3 = account("c")
        acc3["rate_limited_until"] = time.time() + 300  # Cooldown

        self.save_accounts([acc1, acc2, acc3])
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf), \
             mock.patch.object(agy_pool, "get_daemon_pid", return_value=None), \
             mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.list_accounts()
        output = buf.getvalue()
        self.assertIn("* Active", output)
        self.assertIn("Hits: 42", output)
        self.assertIn("Exhausted", output)
        self.assertIn("Hits: 15", output)
        self.assertIn("Cooldown", output)
        self.assertIn("Hits: 0", output)
        self.assertIn("CLI Base Token", output)
        self.assertIn("In Rotation Pool", output)
        self.assertNotIn("Total:", output)
        self.assertNotIn("AI Gen:", output)

    def test_crypto_bundle_round_trip(self):
        msg = b"secret-oauth-data-12345"
        enc = agy_pool.encrypt_bundle(msg, "pass123")
        self.assertEqual(enc["format"], "agy-pool-encrypted-v1")
        dec = agy_pool.decrypt_bundle(enc, "pass123")
        self.assertEqual(dec, msg)

        with self.assertRaises(ValueError):
            agy_pool.decrypt_bundle(enc, "wrong-pass")

        # Tamper tag
        tampered = dict(enc, tag=base64.b64encode(b"0" * 32).decode("ascii"))
        with self.assertRaises(ValueError):
            agy_pool.decrypt_bundle(tampered, "pass123")

    def test_export_and_import_plain(self):
        acc1 = account("a")
        acc1["name"] = "Alice"
        acc1["gen_count"] = 10
        acc1["request_count"] = 25
        acc2 = account("b")
        acc2["name"] = "Bob"
        self.save_accounts([acc1, acc2])

        export_file = os.path.join(self.temp.name, "backup.json")
        res = agy_pool.export_pool(export_file)
        self.assertTrue(res)
        self.assertTrue(os.path.exists(export_file))
        self.assertEqual(os.stat(export_file).st_mode & 0o777, 0o600)

        with open(export_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["accounts"]), 2)
        self.assertEqual(data["strategy"], "max_quota")
        self.assertEqual(data["active_account_email"], "a@example.test")

        # Now wipe local pool and import with replace
        self.save_accounts([])
        res = agy_pool.import_pool(export_file, replace=True)
        self.assertTrue(res)
        restored = agy_pool.load_pool()["accounts"]
        self.assertEqual(len(restored), 2)
        self.assertEqual(restored[0]["email"], "a@example.test")
        self.assertEqual(restored[1]["email"], "b@example.test")
        self.assertEqual(restored[0]["name"], "Alice")
        self.assertEqual(restored[0]["gen_count"], 10)

    def test_export_and_import_encrypted(self):
        acc = account("a")
        self.save_accounts([acc])

        enc_file = os.path.join(self.temp.name, "backup.enc")
        res = agy_pool.export_pool(enc_file, encrypt=True, password="mypassword")
        self.assertTrue(res)

        with open(enc_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual(raw["format"], "agy-pool-encrypted-v1")

        # Test import wrong password
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            res = agy_pool.import_pool(enc_file, password="badpass")
        self.assertFalse(res)

        # Test import correct password
        self.save_accounts([])
        res = agy_pool.import_pool(enc_file, password="mypassword")
        self.assertTrue(res)
        self.assertEqual(len(agy_pool.load_pool()["accounts"]), 1)

    def test_import_merge_and_skip_existing(self):
        acc1 = account("a", token="old-token")
        acc1["name"] = "Alice Old"
        self.save_accounts([acc1])

        backup_accounts = [
            {
                "email": "a@example.test",
                "name": "Alice Updated",
                "refresh_token": "new-refresh-a",
                "access_token": "new-token-a",
                "token_expiry": time.time() + 7200,
            },
            {
                "email": "b@example.test",
                "name": "Bob",
                "refresh_token": "refresh-b",
            }
        ]
        backup_file = os.path.join(self.temp.name, "merge_backup.json")
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "accounts": backup_accounts}, f)

        agy_pool.import_pool(backup_file)
        pool = agy_pool.load_pool()["accounts"]
        self.assertEqual(len(pool), 2)
        acc_a = next(a for a in pool if a["email"] == "a@example.test")
        self.assertEqual(acc_a["refresh_token"], "new-refresh-a")
        self.assertEqual(acc_a["access_token"], "new-token-a")

        # Test skip-existing
        backup_accounts[0]["refresh_token"] = "should-not-apply"
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "accounts": backup_accounts}, f)
        agy_pool.import_pool(backup_file, skip_existing=True)
        pool = agy_pool.load_pool()["accounts"]
        acc_a = next(a for a in pool if a["email"] == "a@example.test")
        self.assertEqual(acc_a["refresh_token"], "new-refresh-a")

    def test_daemon_info_and_outdated_detection(self):
        agy_pool.ensure_dirs()
        # 1. Non-existent PID file
        if os.path.exists(agy_pool.PID_FILE):
            os.unlink(agy_pool.PID_FILE)
        self.assertIsNone(agy_pool.get_daemon_info())

        # 2. Legacy integer PID file
        my_pid = os.getpid()
        with open(agy_pool.PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(my_pid))
        info = agy_pool.get_daemon_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["pid"], my_pid)
        self.assertIsNone(info["version"])

        # 3. Structured JSON PID file
        meta = {"pid": my_pid, "version": agy_pool.VERSION, "script_mtime": int(time.time()) + 1000}
        with open(agy_pool.PID_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        info = agy_pool.get_daemon_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["pid"], my_pid)
        self.assertEqual(info["version"], agy_pool.VERSION)

        # 4. Outdated detection
        with mock.patch.object(agy_pool, "is_port_listening", return_value=True):
            # Same version, future script_mtime -> not outdated
            self.assertFalse(agy_pool.is_daemon_outdated())

            # Older version -> outdated
            meta["version"] = "0.1.0-alpha1"
            with open(agy_pool.PID_FILE, "w", encoding="utf-8") as f:
                json.dump(meta, f)
            self.assertTrue(agy_pool.is_daemon_outdated())

            # Outdated mtime -> outdated
            meta["version"] = agy_pool.VERSION
            meta["script_mtime"] = 100  # long past
            with open(agy_pool.PID_FILE, "w", encoding="utf-8") as f:
                json.dump(meta, f)
            self.assertTrue(agy_pool.is_daemon_outdated())

    def test_ensure_daemon_running_hot_reloads_outdated_daemon(self):
        with mock.patch.object(agy_pool, "is_daemon_running", return_value=True), \
             mock.patch.object(agy_pool, "is_daemon_outdated", return_value=True), \
             mock.patch.object(agy_pool, "get_daemon_pid", return_value=1234), \
             mock.patch.object(agy_pool, "stop_proxy_daemon") as mock_stop, \
             mock.patch.object(agy_pool, "start_proxy_daemon") as mock_start, \
             mock.patch("time.sleep"):
            agy_pool.ensure_daemon_running()
            mock_stop.assert_called_once()
            mock_start.assert_called_once_with(foreground=False)

    def test_cli_version_command(self):
        buf = io.StringIO()
        with mock.patch("sys.argv", ["agy-pool", "version"]), \
             mock.patch("sys.stdout", buf):
            agy_pool.main()
        self.assertIn(f"agy-pool {agy_pool.VERSION}", buf.getvalue())

    def test_display_account_name_resolution(self):
        # 1. Explicit friendly name
        self.assertEqual(agy_pool.display_account_name({"name": "Work", "id": "acc_1", "email": "user@secret.com"}), "Work")
        self.assertEqual(agy_pool.display_account_name({"name": "  Project Lead  ", "id": "acc_2"}), "Project Lead")
        # 2. Safe fallback for acc_N
        self.assertEqual(agy_pool.display_account_name({"name": None, "id": "acc_1", "email": "user@secret.com"}), "Account 1")
        self.assertEqual(agy_pool.display_account_name({"name": "", "id": "acc_42", "email": "user@secret.com"}), "Account 42")
        # 3. Generic safe fallback
        self.assertEqual(agy_pool.display_account_name({"name": None, "id": "custom_uuid", "email": "user@secret.com"}), "Account")
        self.assertEqual(agy_pool.display_account_name({}), "Account")
        self.assertEqual(agy_pool.display_account_name(None), "Account")
        self.assertEqual(agy_pool.display_account_name("invalid"), "Account")

    def test_list_accounts_privacy_and_target_filtering(self):
        acc1 = account("acc_1")
        acc1["email"] = "supersecret_alpha@example.org"
        acc1["name"] = "Production Cloud"
        acc1["gen_count"] = 12

        acc2 = account("acc_2")
        acc2["email"] = "confidential_beta@enterprise.com"
        acc2["name"] = None
        acc2["gen_count"] = 7

        self.save_accounts([acc1, acc2], active="acc_1")

        # Full listing
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf), \
             mock.patch.object(agy_pool, "get_daemon_pid", return_value=None), \
             mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.list_accounts()
        output = buf.getvalue()

        self.assertIn("[1] Production Cloud", output)
        self.assertIn("[2] Account 2", output)
        self.assertNotIn("supersecret_alpha@example.org", output)
        self.assertNotIn("supersecret_alpha", output)
        self.assertNotIn("confidential_beta@enterprise.com", output)
        self.assertNotIn("confidential_beta", output)

        # Filtered by target index
        buf_idx = io.StringIO()
        with mock.patch("sys.stdout", buf_idx), \
             mock.patch.object(agy_pool, "get_daemon_pid", return_value=None), \
             mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.list_accounts("1")
        out_idx = buf_idx.getvalue()
        self.assertIn("[1] Production Cloud", out_idx)
        self.assertNotIn("Account 2", out_idx)
        self.assertNotIn("supersecret_alpha", out_idx)

        # Filtered by email target input (matching succeeds, but email is NEVER echoed in output)
        buf_email = io.StringIO()
        with mock.patch("sys.stdout", buf_email), \
             mock.patch.object(agy_pool, "get_daemon_pid", return_value=None), \
             mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.list_accounts("confidential_beta@enterprise.com")
        out_email = buf_email.getvalue()
        self.assertIn("Account 2", out_email)
        self.assertNotIn("Production Cloud", out_email)
        self.assertNotIn("confidential_beta@enterprise.com", out_email)
        self.assertNotIn("confidential_beta", out_email)

        # Filtered by friendly name target input
        buf_name = io.StringIO()
        with mock.patch("sys.stdout", buf_name), \
             mock.patch.object(agy_pool, "get_daemon_pid", return_value=None), \
             mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.list_accounts("Production Cloud")
        out_name = buf_name.getvalue()
        self.assertIn("[1] Production Cloud", out_name)
        self.assertNotIn("Account 2", out_name)
        self.assertNotIn("supersecret_alpha", out_name)

    def test_account_management_privacy_with_real_email_targets(self):
        acc1 = account("acc_1")
        acc1["email"] = "alice_dev@corp.internal"
        acc1["name"] = None

        acc2 = account("acc_2")
        acc2["email"] = "bob_ops@corp.internal"
        acc2["name"] = "Operations Lead"

        self.save_accounts([acc1, acc2], active="acc_1")

        # switch using real email target
        buf_sw = io.StringIO()
        with mock.patch("sys.stdout", buf_sw), mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.switch_account("bob_ops@corp.internal")
        out_sw = buf_sw.getvalue()
        self.assertIn("Operations Lead", out_sw)
        self.assertNotIn("bob_ops@corp.internal", out_sw)
        self.assertNotIn("bob_ops", out_sw)
        self.assertEqual(agy_pool.load_pool()["active_account_id"], "acc_2")

        # switch using friendly name
        buf_sw_name = io.StringIO()
        with mock.patch("sys.stdout", buf_sw_name), mock.patch.object(agy_pool, "_safe_quota"):
            agy_pool.switch_account("Operations Lead")
        out_sw_name = buf_sw_name.getvalue()
        self.assertIn("Operations Lead", out_sw_name)
        self.assertNotIn("bob_ops", out_sw_name)

        # remove using real email target
        buf_rm = io.StringIO()
        with mock.patch("sys.stdout", buf_rm):
            agy_pool.remove_account("alice_dev@corp.internal")
        out_rm = buf_rm.getvalue()
        self.assertIn("Account 1", out_rm)
        self.assertNotIn("alice_dev@corp.internal", out_rm)
        self.assertNotIn("alice_dev", out_rm)
        pool = agy_pool.load_pool()
        self.assertEqual(len(pool["accounts"]), 1)
        self.assertEqual(pool["accounts"][0]["name"], "Operations Lead")

        # remove using friendly name
        buf_rm_name = io.StringIO()
        with mock.patch("sys.stdout", buf_rm_name):
            agy_pool.remove_account("Operations Lead")
        out_rm_name = buf_rm_name.getvalue()
        self.assertIn("Operations Lead", out_rm_name)
        self.assertNotIn("bob_ops", out_rm_name)
        self.assertEqual(len(agy_pool.load_pool()["accounts"]), 0)

    def test_uncommitted_transport_error_predicates(self):
        # Provably uncommitted failures
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            urllib.error.URLError(ssl.SSLError("TLS handshake failed"))))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            urllib.error.URLError(OSError(errno.ENETUNREACH, "Network is unreachable"))))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            urllib.error.URLError(OSError(errno.EHOSTUNREACH, "No route to host"))))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            ConnectionRefusedError(111, "Connection refused")))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            socket.gaierror(-2, "Name or service not known")))
        self.assertTrue(agy_pool._is_uncommitted_transport_error(
            ssl.SSLError("TLS handshake failed")))

        # Ambiguous failures (must NOT qualify as uncommitted)
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            socket.timeout("timed out")))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            TimeoutError("timed out")))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            urllib.error.URLError(socket.timeout("timed out"))))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            http.client.RemoteDisconnected("Remote end closed connection without response")))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            ConnectionResetError("Connection reset by peer")))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            http.client.IncompleteRead(b"", 100)))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            http.client.BadStatusLine("???")))
        self.assertFalse(agy_pool._is_uncommitted_transport_error(
            urllib.error.HTTPError("http://example.test", 403, "Forbidden", {}, None)))

    def test_uncommitted_transport_failure_fails_over_transparently(self):
        """
        When candidate A encounters a provably uncommitted transport failure,
        the proxy transparently fails over to candidate B and succeeds.
        """
        self.save_accounts([account("a"), account("b")])
        proxy = self.start_server(agy_pool.SmartProxyHandler)
        calls = []

        class DummyResponse:
            status = 200
            def __init__(self, body=b'{"result": "success_b"}'):
                self.headers = email.message.Message()
                self.headers["Content-Type"] = "application/json"
                self._body = io.BytesIO(body)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size=-1):
                return self._body.read(size)
            def read1(self, size=-1):
                return self._body.read(size)

        def urlopen_mock(req, *args, **kwargs):
            auth = req.get_header("Authorization")
            calls.append(auth)
            if "token-a" in auth:
                raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
            return DummyResponse()

        with mock.patch.object(agy_pool.urllib.request, "urlopen", urlopen_mock):
            status, body, _ = self.request(proxy, "/v1internal:generateContent")

        self.assertEqual(status, 200)
        self.assertIn(b"success_b", body)
        self.assertEqual(calls, ["Bearer token-a", "Bearer token-b"])

        # Account A recorded transport error but was NOT locked out as auth error
        pool = agy_pool.load_pool()
        acc_a = next(a for a in pool["accounts"] if a["id"] == "a")
        acc_b = next(a for a in pool["accounts"] if a["id"] == "b")
        self.assertEqual(acc_a.get("error_count"), 1)
        self.assertIsNone(acc_a.get("status"))
        self.assertIsNone(acc_a.get("rate_limited_until"))
        self.assertEqual(acc_b.get("gen_count"), 1)

    def test_all_accounts_uncommitted_transport_failure_returns_503(self):
        """
        When all candidate accounts fail with uncommitted transport failures,
        the proxy returns 503 indicating all accounts exhausted/unavailable.
        """
        self.save_accounts([account("a"), account("b")])
        proxy = self.start_server(agy_pool.SmartProxyHandler)
        calls = []

        def urlopen_mock(req, *args, **kwargs):
            calls.append(req.get_header("Authorization"))
            raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))

        with mock.patch.object(agy_pool.urllib.request, "urlopen", urlopen_mock):
            status, body, _ = self.request(proxy, "/v1internal:generateContent")

        self.assertEqual(status, 503)
        self.assertIn(b"All accounts in pool exhausted or unavailable", body)
        self.assertEqual(len(calls), 2)

    def test_ambiguous_generation_failure_preserves_no_replay_remote_disconnected(self):
        """
        When a generation request fails with RemoteDisconnected (upstream closed after sending),
        the failure is ambiguous: proxy must NOT replay to candidate B, preserving no-replay semantics.
        """
        self.save_accounts([account("a"), account("b")])
        proxy = self.start_server(agy_pool.SmartProxyHandler)
        calls = []

        def urlopen_mock(req, *args, **kwargs):
            calls.append(req.get_header("Authorization"))
            raise http.client.RemoteDisconnected("Remote end closed connection without response")

        with mock.patch.object(agy_pool.urllib.request, "urlopen", urlopen_mock):
            status, _, _ = self.request(proxy, "/v1internal:streamGenerateContent")

        self.assertEqual(status, 502)
        # Only account A was called; account B was never called
        self.assertEqual(calls, ["Bearer token-a"])

    def test_uncommitted_token_refresh_error_does_not_set_auth_error_status(self):
        """
        When token refresh fails with an uncommitted transport error (e.g. DNS failure),
        the account is NOT marked with status='auth_error' and proxy fails over to next account.
        """
        self.save_accounts([account("a"), account("b")])
        proxy = self.start_server(agy_pool.SmartProxyHandler)

        def refresh_mock(acc):
            if acc["id"] == "a":
                raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
            return "token-b"

        class DummyResponse:
            status = 200
            def __init__(self, body=b'{"ok": true}'):
                self.headers = email.message.Message()
                self.headers["Content-Type"] = "application/json"
                self._body = io.BytesIO(body)
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self, size=-1):
                return self._body.read(size)
            def read1(self, size=-1):
                return self._body.read(size)

        with mock.patch.object(agy_pool, "refresh_token", refresh_mock), \
             mock.patch.object(agy_pool.urllib.request, "urlopen", side_effect=lambda *args, **kwargs: DummyResponse()):
            status, body, _ = self.request(proxy, "/v1internal:generateContent")

        self.assertEqual(status, 200)
        self.assertIn(b"ok", body)

        pool = agy_pool.load_pool()
        acc_a = next(a for a in pool["accounts"] if a["id"] == "a")
        self.assertNotEqual(acc_a.get("status"), "auth_error")
        self.assertIsNone(acc_a.get("rate_limited_until"))


if __name__ == "__main__":
    unittest.main()

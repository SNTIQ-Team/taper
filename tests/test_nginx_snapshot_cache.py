"""Exercise the actual deployment location in an isolated nginx + synthetic source.

Run directly with Python's stdlib (no production API, database or pytest needed):
    python3 tests/test_nginx_snapshot_cache.py
Set NGINX_BIN only to choose an already installed nginx executable.
"""
import contextlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


def location_block(config, prefix):
    marker = f'location {prefix} {{'
    start = config.index(marker)
    brace = config.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (config[end] == '{') - (config[end] == '}')
        end += 1
    return config[start:end]


class SnapshotCacheTest(unittest.TestCase):
    def setUp(self):
        nginx = os.environ.get('NGINX_BIN') or shutil.which('nginx')
        if not nginx:
            self.skipTest('nginx is not installed; run this test on the deployment host')
        self.tmp = tempfile.TemporaryDirectory(prefix='q-lwm-nginx-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.link = root / 'web-data'
        for generation in ('web-data.release-one', 'web-data.release-two'):
            (root / generation).mkdir()
        self.switch('web-data.release-one')
        self.state = {'snapshot': 'web-data.release-one', 'requests': 0}
        state = self.state

        class Source(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                state['requests'] += 1
                requested = self.headers.get('If-Kerf-Snapshot')
                status = 409 if requested and requested != state['snapshot'] else 200
                body = json.dumps({'status': 'stale_snapshot' if status == 409 else 'ok',
                                   'snapshot': state['snapshot']}).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'public, max-age=3600')
                if state.get('advertise', True):
                    self.send_header('X-Kerf-Snapshot', state.get('reported', state['snapshot']))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        self.source = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Source)
        thread = threading.Thread(target=self.source.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.source.server_close)
        self.addCleanup(self.source.shutdown)
        config = (Path(__file__).resolve().parents[1] / 'deploy/nginx-api.conf').read_text()
        # Reuse production maps/cache directives and the exact /kerf location;
        # only isolate paths, ports, cache size, timeouts and diagnostic header.
        prefix = config[:config.index('\nserver {')]
        prefix = re.sub(r'proxy_cache_path[^;]+;',
                        f'proxy_cache_path {root}/cache levels=1:2 keys_zone=sntiq_cache:1m max_size=2m use_temp_path=off;', prefix)
        block = location_block(config, '/kerf/')
        block = block.replace('/srv/sntiq-kerf-api/data/web-data;', f'{self.link};')
        block = block.replace('http://127.0.0.1:8002/', f'http://127.0.0.1:{self.source.server_port}/')
        block = block.replace('proxy_read_timeout 30s;', 'proxy_read_timeout 1s; proxy_connect_timeout 1s;')
        block = block[:-1] + 'add_header X-Test-Cache $upstream_cache_status always;\n}'
        with contextlib.closing(socket.socket()) as sock, contextlib.closing(socket.socket()) as legacy:
            sock.bind(('127.0.0.1', 0))
            legacy.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
            self.legacy_port = legacy.getsockname()[1]
        # A second listener seeds a real object under the previous key in the same cache.
        legacy_block = re.sub(r'proxy_cache_key [^;]+;',
                              'proxy_cache_key "v2|$scheme|$request_method|$host|$request_uri|$sntiq_origin_cache_bucket";',
                              block)
        conf = root / 'nginx.conf'
        conf.write_text(f'pid {root}/nginx.pid; error_log {root}/error.log;\n'
                        f'events {{ worker_connections 64; }}\nhttp {{ access_log off;\n'
                        f'{prefix}\nserver {{ listen 127.0.0.1:{self.port}; {block} }}\n'
                        f'server {{ listen 127.0.0.1:{self.legacy_port}; {legacy_block} }}\n}}\n')
        args = [nginx, '-p', str(root), '-c', str(conf)]
        valid = subprocess.run(args + ['-t'], capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.nginx = subprocess.Popen(args + ['-g', 'daemon off; master_process off;'],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop():
            if self.nginx.poll() is None:
                self.nginx.terminate()
                self.nginx.wait(timeout=5)
        self.addCleanup(stop)
        deadline = time.monotonic() + 5
        while True:
            self.assertIsNone(self.nginx.poll(), (root / 'error.log').read_text())
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=.1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    self.fail('isolated nginx did not listen')
                time.sleep(.02)

    def switch(self, generation):
        next_link = self.link.with_name('next')
        next_link.symlink_to(generation)
        next_link.replace(self.link)

    def get(self, pin=None, origin=None, *, port=None):
        headers = {}
        if pin is not None:
            headers['If-Kerf-Snapshot'] = pin
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(f'http://127.0.0.1:{port or self.port}/kerf/acts/synthetic/markdown?norm=1', headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=4)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            try:
                data = json.loads(body)
            except ValueError:
                data = None
            return response.status, data, response.headers.get('X-Test-Cache')

    def warm(self, origin=None):
        status, data, cache = self.get(origin=origin)
        self.assertEqual((status, data['snapshot'], cache), (200, 'web-data.release-one', 'MISS'))
        before = self.state['requests']
        self.assertEqual(self.get(origin=origin)[2], 'HIT')
        self.assertEqual(self.state['requests'], before)

    def test_warm_cache_does_not_ignore_a_snapshot_precondition(self):
        for origin in [None, 'https://sntiq.com']:
            self.warm(origin)
            for pin in ['wrong', '0', 'web-data.release-one']:
                before = self.state['requests']
                status, data, cache = self.get(pin, origin)
                self.assertEqual(status, 200 if pin == 'web-data.release-one' else 409, (pin, cache, data))
                self.assertEqual(cache, 'BYPASS')
                self.assertEqual(self.state['requests'], before + 1)
            self.assertEqual(self.get(origin=origin)[2], 'HIT')

    def test_publication_cannot_serve_or_write_the_wrong_generation(self):
        self.warm()
        self.state['snapshot'] = 'web-data.release-two'
        self.assertEqual(self.get('web-data.release-two'), (200, {'status': 'ok', 'snapshot': 'web-data.release-two'}, 'BYPASS'))
        self.assertEqual(self.get(), (200, {'status': 'ok', 'snapshot': 'web-data.release-one'}, 'HIT'), 'pinned success must not write the ordinary cache')
        self.assertEqual(self.get('web-data.release-one')[0], 409, 'old matching cache must not mask the current worker precondition')
        self.assertEqual(self.get('web-data.release-two')[2], 'BYPASS')

    def test_unpinned_cache_switch_rollback_and_worker_handoff(self):
        self.warm()
        self.switch('web-data.release-two')
        self.assertEqual(self.get()[0], 409, 'the former worker cannot fill the new generation')
        self.assertEqual(self.get('web-data.release-one')[2], 'BYPASS')
        self.state['snapshot'] = 'web-data.release-two'
        self.assertEqual(self.get(), (200, {'status': 'ok', 'snapshot': 'web-data.release-two'}, 'MISS'))
        self.assertEqual(self.get()[2], 'HIT')
        self.assertEqual(self.get('web-data.release-one')[0], 409)
        self.switch('web-data.release-one')
        self.state['snapshot'] = 'web-data.release-one'
        self.assertEqual(self.get(), (200, {'status': 'ok', 'snapshot': 'web-data.release-one'}, 'HIT'))
        self.assertEqual(self.get('web-data.release-two')[0], 409)

    def test_pre_upgrade_unversioned_entry_is_inaccessible_after_switch(self):
        self.assertEqual(self.get(port=self.legacy_port)[2], 'MISS')
        self.assertEqual(self.get(port=self.legacy_port)[2], 'HIT')
        self.switch('web-data.release-two')
        self.state['snapshot'] = 'web-data.release-two'
        self.assertEqual(self.get(port=self.legacy_port)[1]['snapshot'], 'web-data.release-one')
        self.assertEqual(self.get(), (200, {'status': 'ok', 'snapshot': 'web-data.release-two'}, 'MISS'))
        self.assertEqual(self.get()[2], 'HIT')

    def test_missing_or_conflicting_worker_snapshot_is_never_cached(self):
        self.state['advertise'] = False
        for _ in range(2):
            self.assertEqual(self.get()[2], 'MISS')
        self.state.update(advertise=True, reported='web-data.release-two')
        for _ in range(2):
            self.assertEqual(self.get()[2], 'MISS')
        del self.state['reported']
        self.warm()

    def test_source_outage_does_not_substitute_stale_text_for_pinned_request(self):
        self.warm()
        self.source.shutdown()
        self.source.server_close()
        status, data, cache = self.get('web-data.release-one')
        self.assertIn(status, (502, 504))
        self.assertIsNone(data)
        self.assertEqual(cache, 'BYPASS')
        self.assertEqual(self.get()[0], 200, 'ordinary public stale fallback remains available')


if __name__ == '__main__':
    unittest.main(verbosity=2)

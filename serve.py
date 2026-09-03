#!/usr/bin/env python3
"""本地静态服务 + /save 接口，供看板网页直接写 plan_data.json。

用法：
    python3 serve.py [port]      # 默认 8077

- 行为与 `python -m http.server 8077` 一致（静态托管本目录）。
- 额外提供 POST /save：把请求体 JSON 原子写回本目录的 plan_data.json。
- 网页端在点"保存修改"时 POST 当前 boardData 到 /save，即可写文件，无需手动导出。
- 线上 GitHub Pages 是纯静态、没有 /save，网页端会自动降级为仅存 localStorage。
"""
import json
import os
import sys
import tempfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, 'plan_data.json')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # 允许同机不同主机名（127.0.0.1 / localhost）跨域，便于浏览器访问。
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/save':
            self._handle_save()
        else:
            self.send_error(404, 'Not Found')

    def _handle_save(self):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
            raw = self.rfile.read(length) if length else b''
            data = json.loads(raw.decode('utf-8')) if raw else None
            if not isinstance(data, dict) or 'meta' not in data or 'plans' not in data:
                self._json(400, {'ok': False, 'error': 'invalid payload: missing meta/plans'})
                return
            # 原子写：先写临时文件再 rename，避免网页半途读到损坏文件。
            tmp_fd, tmp_path = tempfile.mkstemp(dir=ROOT, suffix='.json.tmp')
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.write('\n')
                os.replace(tmp_path, DATA_FILE)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
            self._json(200, {
                'ok': True,
                'rev': data.get('meta', {}).get('dataRevision'),
                'bytes': os.path.getsize(DATA_FILE),
            })
        except json.JSONDecodeError as e:
            self._json(400, {'ok': False, 'error': f'invalid JSON: {e}'})
        except Exception as e:
            self._json(500, {'ok': False, 'error': str(e)})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write('[serve] ' + (fmt % args) + '\n')


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8077
    server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
    print(f'[serve] plan board on http://127.0.0.1:{port}  (POST /save writes plan_data.json)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[serve] stopped')


if __name__ == '__main__':
    main()

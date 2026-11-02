"""Loopback-only wrapper; accepted functional modules remain byte-for-byte unchanged."""
import argparse
import io
import json
from pathlib import Path
import secrets
import sys
import threading
import zipfile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
FUNCTIONAL = ROOT/'functional'


def functional_modules():
    if str(FUNCTIONAL) not in sys.path:
        sys.path.insert(0, str(FUNCTIONAL))
    import server
    if Path(server.__file__).resolve().parent != FUNCTIONAL:
        raise ValueError('WRONG_SERVER_MODULE; fresh Python process/kernel required')
    return server


def start(workspace, *, pilot=None, image=None, assets_root=None, port=8765):
    base = functional_modules()
    from package_tools import verify
    verify()
    workspace = Path(workspace).resolve()
    if ROOT == workspace or ROOT in workspace.parents:
        raise ValueError('WORKSPACE_OUTSIDE_KIT_REQUIRED')
    # Retain the accepted per-workspace service lock throughout HTTP lifetime.
    lock = (workspace/'service.lock').open('a+b')
    try:
        if sys.platform == 'win32':
            import msvcrt
            lock.write(b'1'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        app = base.Application(workspace)
        if image is None:
            from image_service import ImageService
            image=ImageService(workspace,assets_root=assets_root)
        import image_routes

        class Handler(base.Handler):
            def do_GET(self):
                try:
                    path = urlparse(self.path).path
                    if image_routes.get(self,image,path):return
                    if path=='/app.js':return self.send((ROOT/'web/app.js').read_bytes(),'text/javascript')
                    if path in ('/pilot', '/pilot.js'):
                        name = 'pilot.html' if path == '/pilot' else 'pilot.js'
                        return self.send((ROOT/'web'/name).read_bytes(),
                                         'text/html' if name.endswith('html') else 'text/javascript')
                    if path == '/api/pilot':
                        value = dict(linked=pilot is not None, csrf=app.csrf,
                                     hardware_controls_enabled=pilot is not None,
                                     origin='LIVE_HARDWARE' if pilot else 'NOT_LINKED')
                        if pilot:
                            value['pilot'] = pilot.status()
                        return self.send(value)
                    if path == '/api/pilot/evidence.zip':
                        base.require(pilot is not None, 'HARDWARE_NOT_LINKED')
                        base.require(pilot.join(0), 'WAIT_FOR_TERMINAL_RECORD_BOUNDARY')
                        base.require(pilot.status()['state'] not in ('READY','RUNNING','STOPPING'), 'RUN_NOT_FINISHED')
                        root = Path(pilot.owner.session.root).resolve()
                        buf = io.BytesIO()
                        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                            for p in sorted(root.rglob('*')):
                                if p.is_file():
                                    base.require(root in p.resolve().parents, 'SESSION_EXPORT_PATH')
                                    z.write(p, root.name+'/'+p.relative_to(root).as_posix())
                        return self.send(buf.getvalue(), 'application/zip', filename=root.name+'.zip')
                    if path == '/':
                        page = (FUNCTIONAL/'web/index.html').read_text(encoding='utf-8')
                        if pilot:
                            page = page.replace('硬件执行入口未连接', '四条真实联调已连接（独立页面）')
                        if image.factory is not None:page=page.replace('硬件执行入口未连接','整图真实执行器已连接（上传图片页）')
                        page = page.replace('<nav>', '<nav><a href="/upload" style="padding:12px;color:#9ce7d2">上传图片与板卡测试 →</a><a href="/pilot" style="padding:12px;color:#9ce7d2">四条真实联调 →</a>')
                        return self.send(page.encode('utf-8'), 'text/html')
                    return super().do_GET()
                except Exception as exc:
                    return self.send(dict(error=str(exc)), status=409)

            def do_POST(self):
                try:
                    if image_routes.post(self,image):return
                except Exception as exc:
                    return self.send(dict(error=str(exc),automatic_retry=False),status=409)
                if self.path not in ('/api/pilot/start', '/api/pilot/stop'):
                    if (pilot or image.factory is not None) and self.path in ('/api/start', '/api/submit-mainline'):
                        return self.send(dict(error='LIVE_FIXED_PILOT_PAGE_ONLY; simulations disabled in linked process'), status=409)
                    return super().do_POST()
                try:
                    base.require(pilot is not None, 'HARDWARE_NOT_LINKED')
                    token = self.headers.get('X-Lab-Token', '')
                    base.require(secrets.compare_digest(token, app.csrf), 'LOCAL_SESSION_TOKEN')
                    origin = self.headers.get('Origin')
                    base.require(not origin or urlparse(origin).netloc == self.headers.get('Host'), 'SAME_ORIGIN_REQUIRED')
                    size = int(self.headers.get('Content-Length', '0'))
                    base.require(0 < size <= 4096 and self.headers.get_content_type() == 'application/json', 'BOUNDED_JSON_REQUIRED')
                    body = json.loads(self.rfile.read(size))
                    base.require(set(body) == {'idempotency_key','plan_sha256'}, 'FIXED_PLAN_NO_ARBITRARY_PARAMETERS')
                    return self.send(pilot.command(self.path.rsplit('/', 1)[-1],
                                                   body['idempotency_key'], body['plan_sha256']))
                except Exception as exc:
                    return self.send(dict(error=str(exc), automatic_retry=False), status=409)

        http = base.ThreadingHTTPServer(('127.0.0.1', port), Handler)
        http.daemon_threads = True
        http.app = app
        # Simulations are never executed alongside an owned live board session.
        worker = None
        if pilot is None and image.factory is None:
            worker = threading.Thread(target=app.worker, daemon=True)
            worker.start()
        handle = Handle(http, app, lock, pilot)
        handle.image=image
        handle.thread.start()
        print('上位机：http://127.0.0.1:%d/pilot；真实联调连接=%s' % (http.server_address[1], pilot is not None), flush=True)
        print('上传图片页面：http://127.0.0.1:%d/upload；整图会话连接=%s'%(http.server_address[1],image.factory is not None),flush=True)
        return handle
    except BaseException:
        lock.close()
        raise


class Handle:
    def __init__(self, http, app, lock, pilot):
        self.http, self.app, self.lock, self.pilot = http, app, lock, pilot
        self.thread = threading.Thread(target=http.serve_forever, daemon=True, name='pynq-web-http')

    def shutdown(self):
        image=getattr(self,"image",None)
        if image and image.pilot and not image.pilot.join(0):raise RuntimeError("请先停止图片剩余项并等待当前记录封存")
        if image and image.pilot and image.pilot.status()["state"]=="READY":raise RuntimeError("请先在图片页取消未执行计划")
        if self.pilot and self.pilot.status()['state'] in ('READY','RUNNING','STOPPING'):
            raise RuntimeError('先在真实联调页停止剩余项，待当前记录完成并封存后再关闭服务')
        self.http.shutdown()
        self.thread.join(5)
        self.http.server_close()
        self.app.shutdown.set()
        self.lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--assets-root',type=Path)
    args = parser.parse_args()
    handle = start(args.workspace, port=args.port,assets_root=args.assets_root)
    try:
        handle.thread.join()
    except KeyboardInterrupt:
        handle.shutdown()

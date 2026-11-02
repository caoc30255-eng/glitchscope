"""Bounded HTTP routes for upload/prepare/send/status/download."""
import io
import json
import secrets
from pathlib import Path
from urllib.parse import urlparse,unquote
import zipfile

ROOT=Path(__file__).resolve().parent


def get(handler,image,path):
    if path in ('/upload','/upload.js'):
        filename='upload.html' if path=='/upload' else 'upload.js'
        handler.send((ROOT/'web'/filename).read_bytes(),'text/html' if path=='/upload' else 'text/javascript');return True
    if path=='/api/images/state':
        handler.send(dict(image.status(),csrf=handler.app.csrf));return True
    if path.startswith('/api/images/asset/'):
        parts=path.split('/')
        if len(parts)!=6 or parts[5]!='source.png':raise ValueError('ASSET_PREVIEW_ROUTE')
        asset=image.assets.read(parts[4])
        handler.send(asset['files']['source.png'],'image/png');return True
    if path.startswith('/api/images/artifact/'):
        name=unquote(path[len('/api/images/artifact/'):]);file=image.artifact_path(name)
        handler.send(file.read_bytes(),'image/png' if file.suffix=='.png' else 'application/json' if file.suffix=='.json' else 'application/octet-stream');return True
    if path=='/api/images/session.zip':
        if image.pilot is None or not image.pilot.join(0) or image.pilot.status()['state']=='READY':raise ValueError('WAIT_FOR_IMAGE_TERMINAL_STATE')
        root=Path(image.pilot.owner.session.root).resolve();out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob('*')):
                if p.is_file():
                    if root not in p.resolve().parents:raise ValueError('SESSION_PATH')
                    z.write(p,root.name+'/'+p.relative_to(root).as_posix())
        handler.send(out.getvalue(),'application/zip',filename=root.name+'.zip');return True
    return False


def post(handler,image):
    path=handler.path
    if path not in ('/api/images/upload','/api/images/prepare','/api/images/start','/api/images/stop'):return False
    if not secrets.compare_digest(handler.headers.get('X-Lab-Token',''),handler.app.csrf):raise ValueError('LOCAL_SESSION_TOKEN')
    origin=handler.headers.get('Origin')
    if origin and urlparse(origin).netloc!=handler.headers.get('Host'):raise ValueError('SAME_ORIGIN_REQUIRED')
    size=int(handler.headers.get('Content-Length','0'));limit=12*1024*1024 if path.endswith('/upload') else 4096
    if not 0<size<=limit or handler.headers.get_content_type()!='application/json':raise ValueError('BOUNDED_JSON_REQUIRED')
    body=json.loads(handler.rfile.read(size))
    if path.endswith('/upload'):result=image.upload(body)
    elif path.endswith('/prepare'):result=image.prepare(body)
    else:result=image.command(path.rsplit('/',1)[-1],body)
    handler.send(result);return True

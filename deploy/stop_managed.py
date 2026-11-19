"""Stop only the expected project process; retain PID files on timeout/mismatch."""
import argparse
import os
from pathlib import Path
import signal
import time
from urllib.parse import urlsplit

def process(pid):
    try:
        base=Path('/proc')/str(pid)
        stat=base.joinpath('stat').read_text().split(') ',1)[1].split()
        if stat[0]=='Z':return None
        args=[value.decode() for value in base.joinpath('cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
        return stat[19],args,base.joinpath('cwd').resolve()
    except FileNotFoundError:return None

def expected(name,root,args,cwd):
    root=Path(root).resolve()
    if name=='backend':return '-jar' in args and str(root/'workspace/runtime/releases/backend')+'/' in args[args.index('-jar')+1] and cwd==root
    if name=='detector':return args[0]==str(root/'workspace/runtime/detector-env/bin/python') and args[-1]=='ui.py' and (cwd==root/'RailwayDetector' or root/'workspace/runtime/releases/detector' in cwd.parents)
    if name=='flask':return (args[0]==str(root/'workspace/runtime/flask-venv/bin/python') or 'gunicorn' in ' '.join(args[:2])) and (args[-1]=='app.py' or 'app:app' in args or 'gunicorn' in ' '.join(args[:2])) and (cwd==root/'web-flask' or root/'workspace/runtime/releases/gateway' in cwd.parents)
    if name=='frontend':return str(root/'web-vue/node_modules/vite/bin/vite.js') in args
    if name=='guardian':return str(root/'deploy/guardian.py') in args and cwd==root
    if name in ('demo_stream','user_stream'):
        try:
            source=Path(args[args.index('-i')+1]).resolve();target=urlsplit(args[-1])
            return args[0].startswith(str(root/'workspace/runtime/') ) and 'ffmpeg' in Path(args[0]).name and (source==root/'worker.mp4' or root/'workspace/runtime' in source.parents) and target.scheme=='rtsp' and target.hostname in ('127.0.0.1','localhost','::1') and target.port==8554 and bool(target.path.strip('/'))
        except (ValueError,IndexError):return False
    return False

def stop(name,root,seconds=30):
    root=Path(root).resolve();path=root/'workspace/runtime/pids'/f'{name}.pid'
    if not path.exists():return 'not-managed'
    value=path.read_text().strip()
    if not value.isdigit() or int(value)<=1:raise RuntimeError('invalid PID; file retained')
    pid=int(value);before=process(pid)
    if before is None:path.unlink();return 'already-stopped'
    birth,args,cwd=before
    if not expected(name,root,args,cwd):raise RuntimeError(name+' PID identity mismatch; nothing stopped and PID retained')
    os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        current=process(pid)
        if current is None or current[0]!=birth:path.unlink();return 'stopped'
        time.sleep(.05)
    raise RuntimeError(name+' did not exit; PID retained and dependent services left running')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('name',choices=('guardian','backend','detector','flask','frontend','demo_stream','user_stream'));args=parser.parse_args()
    print(args.name+': '+stop(args.name,Path(__file__).resolve().parents[1]))

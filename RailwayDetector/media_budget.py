"""Local sampled clips: bounded space, opt-in expiry of owned closed clips only."""
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from datetime import datetime

class MediaBudget:
    def __init__(self,root,max_bytes=2_000_000_000_000,retention_days=30,min_free_bytes=128*1024**2):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.max_bytes=int(max_bytes);self.retention_days=int(retention_days);self.min_free=int(min_free_bytes)
        if self.max_bytes<1 or self.retention_days<0 or self.min_free<0:raise ValueError('invalid media budget')
        self.lock=threading.RLock();self.active=set();self.last_prune=0.
        self._sizes={};self._scan_at=0.
    def observe(self,name):
        with self.lock:
            path=self.root/name
            try:self._sizes[name]=path.stat().st_size
            except FileNotFoundError:self._sizes.pop(name,None)
    def used(self):
        with self.lock:
            # Closed segments are immutable. Account new closures immediately;
            # reconcile external deletions once a minute, rather than statting
            # a month's archive on every frame/read-loop iteration.
            if time.monotonic()-self._scan_at>=60 or not self._scan_at:
                sizes={}
                with os.scandir(self.root) as entries:
                    for entry in entries:
                        try:
                            if entry.name.endswith(('.mp4','.analysis.json')) and entry.is_file(follow_symlinks=False):sizes[entry.name]=entry.stat(follow_symlinks=False).st_size
                        except FileNotFoundError:pass
                self._sizes=sizes;self._scan_at=time.monotonic()
            for name in tuple(self.active):self.observe(name)
            return sum(self._sizes.values())
    def allow(self,reservation):
        return self.used()+reservation<=self.max_bytes and shutil.disk_usage(self.root).free-reservation>=self.min_free
    def prune(self,now=None):
        now=time.time() if now is None else now
        if not self.retention_days:return 0
        removed=0
        with self.lock:
            for manifest in self.root.glob('*.railway-clip.json'):
                try:
                    data=json.loads(manifest.read_text());name=data['file']
                    if data.get('ownedBy')!='railway-event-recorder-v1' or not re.fullmatch(r'[A-Za-z0-9_-]+\.mp4',name):continue
                    path=self.root/name
                    if name in self.active or path.is_symlink() or data['closedAt']>now-self.retention_days*86400:continue
                    path.unlink(missing_ok=True);self._sizes.pop(name,None);manifest.unlink();removed+=1
                except (ValueError,KeyError,OSError):continue
            for manifest in self.root.glob('*.full-source.json'):
                try:
                    data=json.loads(manifest.read_text());name=data['file']
                    if data.get('kind')!='FULL_SOURCE' or not re.fullmatch(r'[A-Za-z0-9_-]+\.mp4',name):continue
                    path=self.root/name
                    if name in self.active or path.is_symlink() or datetime.fromisoformat(data['endedAt'].replace('Z','+00:00')).timestamp()>now-self.retention_days*86400:continue
                    path.unlink(missing_ok=True);self._sizes.pop(name,None);manifest.unlink();removed+=1
                except (ValueError,KeyError,OSError):continue
            for manifest in self.root.glob('*.analysis.json'):
                try:
                    data=json.loads(manifest.read_text())['registration'];name=data['file']
                    if data.get('kind')!='DETECTION_SAMPLES' or not re.fullmatch(r'[A-Za-z0-9_-]+\.mp4',name):continue
                    path=self.root/name
                    if name in self.active or path.is_symlink() or datetime.fromisoformat(data['endedAt'].replace('Z','+00:00')).timestamp()>now-self.retention_days*86400:continue
                    path.unlink(missing_ok=True);self._sizes.pop(name,None);manifest.unlink();self._sizes.pop(manifest.name,None);removed+=1
                except (ValueError,KeyError,OSError):continue
            for marker in self.root.glob('*.analysis.writing.json'):
                try:
                    data=json.loads(marker.read_text());name=data['file']
                    if data.get('ownedBy')!='railway-analysis-v1' or not re.fullmatch(r'[A-Za-z0-9_-]+\.mp4',name) or data['started']>now-self.retention_days*86400:continue
                    path=self.root/name
                    if name in self.active or path.is_symlink():continue
                    path.unlink(missing_ok=True);self._sizes.pop(name,None);marker.unlink();removed+=1
                except (ValueError,KeyError,OSError):continue
        return removed

_budgets={};_guard=threading.Lock()
def recording_budget(root):
    root=str(Path(root).resolve())
    with _guard:
        if root not in _budgets:_budgets[root]=MediaBudget(root,int(os.getenv('RECORDING_MAX_BYTES','2000000000000'))-int(os.getenv('EVIDENCE_MAX_BYTES','1073741824')),int(os.getenv('RECORDING_RETENTION_DAYS','30')),int(os.getenv('RECORDING_MIN_FREE_BYTES','1073741824')))
        return _budgets[root]

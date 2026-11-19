"""Small real-weight regression; no MQTT, live cameras or business database."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import time

import cv2
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'RailwayDetector'))
config = Path(tempfile.gettempdir())/'railway-fix-real-model'
config.mkdir(exist_ok=True)
os.environ['YOLOV5_CONFIG_DIR']=str(config/'yolo')
os.environ['MPLCONFIGDIR']=str(config/'matplotlib')
# Reuse the existing deployment font; regression tests must not download assets.
(config/'yolo').mkdir(exist_ok=True)
shutil.copy2(ROOT/'workspace/runtime/config/yolov5/Arial.ttf',config/'yolo/Arial.ttf')
os.environ['RAILWAY_DEVICE']='cpu'
weights=ROOT/'RailwayDetector/models/best1030.pt'
os.environ['RAILWAY_MODEL_PATH']=str(weights)
EXPECTED='f9887d1699275990353fa03fa721251a955b257a6571e0c4762365a38ede0052'

def run():
    torch.set_num_threads(2)
    digest=hashlib.sha256(weights.read_bytes()).hexdigest()
    assert digest==EXPECTED
    video=ROOT/'workspace/runtime/smoke-cow-short.mp4'
    cap=cv2.VideoCapture(str(video))
    samples=[]
    try:
        index=0
        while len(samples)<3:
            ok,frame=cap.read()
            if not ok:break
            if index in (0,10,20):samples.append(frame)
            index+=1
    finally:cap.release()
    assert samples
    original=subprocess.check_output(['git','show',
        '086b8df813ebaaf9e69b8d29f07fd98363531d49:RailwayDetector/model_init.py'],cwd=str(ROOT)).decode()
    baseline={'__name__':'railway_baseline','__file__':str(ROOT/'RailwayDetector/model_init.py')}
    exec(compile(original,'baseline_model_init.py','exec'),baseline)
    from model_init import Detector
    detector=Detector(model=baseline['model'],device='cpu')
    matches=[];timings=[]
    for frame in samples:
        expected,_=baseline['predict'](frame)
        start=time.perf_counter();actual=detector.detect(frame);timings.append(time.perf_counter()-start)
        assert len(actual)==len(expected),(len(actual),len(expected))
        unmatched=list(actual)
        for row in expected:
            p=row['location']
            bbox=np.array([p['center_x']-p['width']/2,p['center_y']-p['height']/2,
                           p['center_x']+p['width']/2,p['center_y']+p['height']/2])
            candidates=[d for d in unmatched if d.class_name==row['objectDetect']
                        and np.max(np.abs(np.array(d.bbox)-bbox))<=.501
                        and round(d.confidence,2)==row['score']]
            assert candidates, row
            unmatched.remove(candidates[0])
        matches.append(len(actual))
    assert sum(matches)>0,'fixture must exercise a positive detection'
    shapes=[(640,360),(360,640),(640,640),(960,540)]
    images=[cv2.resize(samples[0],shape) for shape in shapes]
    serial=[detector.detect(image) for image in images]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        parallel=list(pool.map(detector.detect,images))
    for expected,actual in zip(serial,parallel):
        assert len(expected)==len(actual)
        for a,b in zip(expected,actual):
            assert a.class_name==b.class_name
            assert abs(a.confidence-b.confidence)<1e-5
            np.testing.assert_allclose(a.bbox,b.bbox,atol=1e-3,rtol=0)
    assert hashlib.sha256(weights.read_bytes()).hexdigest()==EXPECTED
    report={'weight_sha256':digest,'torch':torch.__version__,'device':'cpu',
            'baseline_commit':'086b8df813ebaaf9e69b8d29f07fd98363531d49',
            'sample_frames':len(samples),'detections_per_frame':matches,
            'single_pass_seconds':timings,'mixed_shape_parallel_cases':len(images),
            'serial_parallel_equivalent':True,'weights_unchanged':True}
    destination=ROOT/'workspace/runtime/bugfix-tests'
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'real-model-smoke.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':run()

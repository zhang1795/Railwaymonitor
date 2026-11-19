"""Bounded video reads in a disposable decoder process (also for old OpenCV)."""
import multiprocessing
import os
import queue
import threading
import time
from urllib.parse import urlsplit
import cv2
from strict_capture import StrictCapture,FrameDecodeError,SourceUnavailableError

def _latest_loop(connection, cap):
    """One continuously replaced live frame; IPC backpressure cannot stop decoding."""
    condition=threading.Condition()
    current={'sequence':0,'frame':None,'pts':0.,'received':0.,'ended':False,'error':None}
    def decode():
        try:
            while True:
                ok,frame=cap.read()
                if not ok or frame is None:break
                received=time.time();pts=cap.get(cv2.CAP_PROP_POS_MSEC)
                with condition:
                    current.update(sequence=current['sequence']+1,frame=frame,pts=pts,received=received)
                    condition.notify_all()
        except (FrameDecodeError,SourceUnavailableError) as error:
            with condition:current['error']='decode_error' if isinstance(error,FrameDecodeError) else 'source_error';condition.notify_all()
        finally:
            cap.release()
            with condition:current['ended']=True;condition.notify_all()
    threading.Thread(target=decode,name='latest-frame',daemon=True).start()
    last=0
    while True:
        request=connection.recv()
        modern=isinstance(request,dict) and request.get('action')=='read' and request.get('protocol')==2
        if request!='read' and not modern:break
        with condition:
            condition.wait_for(lambda:current['sequence']>last or current['ended'] or current['error'])
            if current['error']:
                connection.send((current['error'],None) if modern else (False,None,0.));break
            sequence=current['sequence']
            if sequence==last:
                reply=(False,None,0.,time.time(),0,sequence)
            else:
                reply=(True,current['frame'],current['pts'],current['received'],max(0,sequence-last-1),sequence)
            last=sequence
        if modern:
            reply=reply+({'decodeErrors':getattr(cap,'rejected_frames',0),'checked':getattr(cap,'checked',False),'relativeLagMs':getattr(cap,'relative_lag_ms',0.)},)
        connection.send(reply if modern else reply[:3])
        if not reply[0]:break

def _reader_main(connection, url):
    cap = None
    try:
        # Native decoder diagnostics can contain camera credentials. Report only
        # bounded, generic failures to the parent, never raw source URLs.
        with open(os.devnull,'w') as output:os.dup2(output.fileno(),2)
        os.environ.setdefault('OPENCV_FFMPEG_CAPTURE_OPTIONS','rtsp_transport;tcp')
        cv2.setNumThreads(1)
        live=urlsplit(str(url)).scheme.lower() in ('rtsp','rtsps')
        cap = StrictCapture(url) if live else cv2.VideoCapture(url)
        connection.send((cap.isOpened(), {key:cap.get(key) for key in
                         (cv2.CAP_PROP_FPS,cv2.CAP_PROP_FRAME_WIDTH,cv2.CAP_PROP_FRAME_HEIGHT)}))
        if cap.isOpened() and live:
            live_cap=cap;cap=None  # the decoder thread owns release/read
            _latest_loop(connection,live_cap)
            return
        while cap.isOpened():
            request=connection.recv()
            if request!='read' and request!={'action':'read','protocol':2}:break
            ok, image = cap.read()
            connection.send((ok,image,cap.get(cv2.CAP_PROP_POS_MSEC)))
            if not ok:
                break
    except FrameDecodeError:
        try:connection.send(('decode_error',None))
        except (OSError,EOFError):pass
    except SourceUnavailableError:
        try:connection.send(('source_error',None))
        except (OSError,EOFError):pass
    except (EOFError,BrokenPipeError):
        pass
    except Exception:
        try: connection.send(('error',None))
        except (OSError,EOFError): pass
    finally:
        if cap is not None: cap.release()
        connection.close()

def _decoder_entry(connection,url,parent,target):
    # A hard-killed parent must not leave a native decoder with an open camera.
    if __import__('sys').platform.startswith('linux'):
        import ctypes,signal
        if ctypes.CDLL(None).prctl(1,signal.SIGTERM)!=0 or os.getppid()!=parent:
            connection.close();return
    target(connection,url)

class BoundedCapture:
    def __init__(self, url, stop_event=None, timeout=5, target=_reader_main):
        self.stop_event = stop_event
        self.timeout = timeout
        self._opened = False
        self._released = False
        self._properties = {}
        self.frame_received_at=None
        self.decoded_frames=0
        self.skipped_frames=0
        self.decode_errors=0
        self.decode_checked=False
        self.relative_lag_ms=0.
        self._responses=queue.Queue(maxsize=1)
        self._receiver=None
        context = multiprocessing.get_context('spawn')
        self._connection, child = context.Pipe()
        self._process = context.Process(target=_decoder_entry,args=(child,url,os.getpid(),target),daemon=True)
        try:
            self._process.start()
            child.close()
            self._receiver=threading.Thread(target=self._pump,name='decoder-ipc',daemon=True)
            self._receiver.start()
            opened, properties = self._receive()
            if not isinstance(opened,bool):
                raise RuntimeError('decoder failed during startup')
            self._opened, self._properties = opened, properties
            if not opened:
                self.release()
        except BaseException:
            child.close()
            self.release()
            raise

    def _pump(self):
        try:
            while not self._released:
                reply=self._connection.recv()
                while not self._released:
                    try:self._responses.put(reply,timeout=.05);break
                    except queue.Full:pass
        except (EOFError,OSError,ValueError):
            while not self._released:
                try:self._responses.put(None,timeout=.05);break
                except queue.Full:pass

    def _receive(self):
        deadline = time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            if self.stop_event is not None and self.stop_event.is_set():
                raise InterruptedError('video task stopped')
            try:
                reply=self._responses.get(timeout=min(.05,max(0,deadline-time.monotonic())))
                if reply is None:raise RuntimeError('decoder exited unexpectedly')
                if isinstance(reply,tuple) and len(reply)==2 and reply[0]=='decode_error':
                    self.decode_errors+=1;raise FrameDecodeError()
                if isinstance(reply,tuple) and len(reply)==2 and reply[0]=='source_error':
                    raise SourceUnavailableError('video source unavailable')
                return reply
            except queue.Empty:pass
        raise TimeoutError('video open/read timed out')

    def isOpened(self):
        return self._opened and not self._released

    def get(self, key):
        return self._properties.get(key,0.)

    def read(self):
        if not self.isOpened():
            return False,None
        self._connection.send({'action':'read','protocol':2})
        reply = self._receive()
        if len(reply) not in (3,6,7):
            raise RuntimeError('decoder failed during read')
        ok, frame, pts = reply[:3]
        self.frame_received_at=reply[3] if len(reply)>=6 else time.time()
        self.decoded_frames=reply[5] if len(reply)>=6 else self.decoded_frames+int(bool(ok))
        if len(reply)>=6:self.skipped_frames+=reply[4]
        if len(reply)==7:self.decode_errors=reply[6]['decodeErrors'];self.decode_checked=reply[6]['checked'];self.relative_lag_ms=reply[6].get('relativeLagMs',0.)
        self._properties[cv2.CAP_PROP_POS_MSEC] = pts
        return ok,frame

    def release(self):
        if self._released:
            return
        self._released = True
        self._opened = False
        try: self._connection.close()
        finally:
            if self._process.pid is not None:
                self._process.join(.1)
                if self._process.is_alive():
                    self._process.terminate()
                    self._process.join(1)
                if self._process.is_alive():
                    self._process.kill()
                    self._process.join(1)
                self._process.close()
            if self._receiver is not None:self._receiver.join(.5)

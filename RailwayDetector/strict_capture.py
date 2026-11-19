"""Decode live sources without passing FFmpeg's concealed corrupt frames to AI.

Each instance lives in the existing disposable decoder process. Logs are captured
as signals only: native text can contain private source credentials.
"""
import cv2
import errno
import os,time

class FrameDecodeError(RuntimeError):
    def __init__(self,message='video decoding failed; corrupted input was rejected'):
        super().__init__(message)

class SourceUnavailableError(RuntimeError):
    pass

class StrictCapture:
    def __init__(self,url,*,opener=None):
        import av
        self.av=av;self.container=None;self.frames=None;self.checked=False
        self.last_pts=0.;self.rejected_frames=0;self.opened=False
        self.log_capture=None;self.logs=[];self.relative_lag_ms=0.;self.anchor=None
        av.logging.set_level(av.logging.ERROR)
        try:
            # Startup probing may encounter partial GOPs after joining a live
            # stream. No probe image is ever published; read() waits for a clean
            # key frame. Invalid pictures after startup fail the whole session.
            with av.logging.Capture(local=False):
                self.container=(opener or av.open)(url,mode='r',options={'rtsp_transport':'tcp'},timeout=(4.,4.))
            if not self.container.streams.video:raise FrameDecodeError('source has no video stream')
            self.stream=self.container.streams.video[0]
            self.width,self.height=self.stream.codec_context.width,self.stream.codec_context.height
            if self.width<1 or self.height<1 or self.width*self.height>16_777_216:
                raise SourceUnavailableError('unsupported source dimensions')
            self.stream.codec_context.thread_count=max(1,min(8,int(os.getenv('VIDEO_DECODE_THREADS','4'))))
            self.stream.codec_context.thread_type='FRAME'
            self.stream.codec_context.options=dict(self.stream.codec_context.options,err_detect='explode')
            self.packets=iter(self.container.demux(self.stream));self.pending=[]
            self.waiting_keyframe=True;self.input_key_seen=False
            self.log_capture=av.logging.Capture(local=False);self.logs=self.log_capture.__enter__()
            self.opened=True
        except FrameDecodeError:
            self.release();raise
        except Exception:
            self.release();raise SourceUnavailableError('video source unavailable during decoder startup') from None

    def isOpened(self):return self.opened
    def get(self,key):
        if key==cv2.CAP_PROP_FPS:return float(self.stream.average_rate or self.stream.guessed_rate or 25.)
        if key==cv2.CAP_PROP_FRAME_WIDTH:return self.stream.codec_context.width
        if key==cv2.CAP_PROP_FRAME_HEIGHT:return self.stream.codec_context.height
        if key==cv2.CAP_PROP_POS_MSEC:return self.last_pts
        return 0.

    def _reject(self):
        self.rejected_frames+=1
        # Before the first clean keyframe, discard the incomplete startup GOP.
        # Do not fabricate an empty observation or conceal the damage with pixels.
        if self.waiting_keyframe:
            self.stream.codec_context.flush_buffers();self.pending.clear();self.input_key_seen=False;return
        raise FrameDecodeError()

    def _check_errors(self):
        if getattr(self,'logs',None):
            self.logs.clear();self._reject();return True
        return False

    def read(self):
        while self.opened:
            if self.pending:
                if self._check_errors():continue
                frame=self.pending.pop(0)
                if frame.width!=self.width or frame.height!=self.height:
                    raise SourceUnavailableError('source dimensions changed; reconnect required')
                if frame.is_corrupt:
                    self._reject();continue
                if self.waiting_keyframe:
                    if not frame.key_frame:continue
                    self.waiting_keyframe=False
                with self.av.logging.Capture(local=False) as logs:
                    image=frame.to_ndarray(format='bgr24')
                if logs or image is None or not image.size:
                    self._reject();continue
                self.checked=True
                if frame.time is not None:
                    self.last_pts=float(frame.time)*1000
                    now=time.monotonic()
                    if self.anchor is None:self.anchor=(now,float(frame.time))
                    self.relative_lag_ms=max(0.,(now-self.anchor[0]-(float(frame.time)-self.anchor[1]))*1000)
                    if self.relative_lag_ms>float(os.getenv('VIDEO_MAX_RELATIVE_LAG_MS','2000')):
                        raise SourceUnavailableError('decoder backlog exceeded freshness limit; reconnect required')
                return True,image
            try:
                with self.av.logging.Capture(local=False) as logs:
                    packet=next(self.packets)
                if logs:
                    self._reject();continue
                if self._check_errors():continue
                if self.waiting_keyframe and not self.input_key_seen and not packet.is_keyframe:continue
                if packet.is_keyframe:self.input_key_seen=True
                if packet.is_corrupt:
                    self._reject();continue
                try:
                    with self.av.logging.Capture(local=False) as logs:
                        frames=packet.decode()
                except self.av.error.FFmpegError:
                    self._reject();continue
                if logs:
                    self._reject();continue
                if self._check_errors():continue
                self.pending.extend(frames)
            except StopIteration:return False,None
            except FrameDecodeError:raise
            except self.av.error.FFmpegError as error:
                if getattr(error,'errno',None) in (errno.ETIMEDOUT,errno.ECONNRESET,errno.ECONNREFUSED,errno.EIO,1414092869):
                    raise SourceUnavailableError('video transport interrupted') from None
                self._reject()
        return False,None

    def release(self):
        self.opened=False
        if self.container is not None:
            self.container.close();self.container=None
        if self.log_capture is not None:
            self.log_capture.__exit__(None,None,None);self.log_capture=None

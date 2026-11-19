import sys,unittest,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np,av
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from strict_capture import StrictCapture,FrameDecodeError,SourceUnavailableError
from video_capture import BoundedCapture,_latest_loop

class DamagedSource:
    def read(self):raise FrameDecodeError()
    def get(self,key):return 0.
    def release(self):pass

def corrupt_reader(connection,url):
    connection.send((True,{}));_latest_loop(connection,DamagedSource())

class StrictDecodeTests(unittest.TestCase):
    def test_real_file_decodes_only_valid_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'input.mp4');writer=cv2.VideoWriter(path,cv2.VideoWriter_fourcc(*'mp4v'),6,(96,64))
            for i in range(12):writer.write(np.full((64,96,3),i*10,np.uint8))
            writer.release();capture=StrictCapture(path)
            try:
                count=0
                while True:
                    ok,frame=capture.read()
                    if not ok:break
                    count+=1;self.assertEqual(frame.shape,(64,96,3));self.assertTrue(capture.checked)
                self.assertEqual(count,12)
            finally:capture.release()
    def test_decoder_damage_is_not_converted_to_an_empty_frame_or_timeout(self):
        capture=BoundedCapture('unused',target=corrupt_reader)
        try:
            with self.assertRaises(FrameDecodeError):capture.read()
            self.assertEqual(capture.decode_errors,1)
        finally:capture.release()
    def test_a_flagged_picture_is_rejected_before_conversion(self):
        capture=StrictCapture.__new__(StrictCapture);capture.av=av;capture.opened=True;capture.width=96;capture.height=64;capture.rejected_frames=0;capture.waiting_keyframe=False
        class Picture:
            is_corrupt=True;width=96;height=64
            def to_ndarray(self,**kwargs):raise AssertionError('corrupt pixels must never be delivered')
        capture.pending=[Picture()]
        with self.assertRaises(FrameDecodeError):capture.read()
        self.assertEqual(capture.rejected_frames,1)
    def test_decoder_errors_without_corrupt_flag_are_still_rejected(self):
        capture=StrictCapture.__new__(StrictCapture);capture.av=av;capture.opened=True;capture.rejected_frames=0;capture.waiting_keyframe=False;capture.pending=[]
        class Packet:
            is_corrupt=False;is_keyframe=True
            def decode(self):
                av.logging.log(av.logging.ERROR,'h264','test-only damaged bitstream')
                return []
        capture.packets=iter([Packet()]);av.logging.set_level(av.logging.ERROR)
        with self.assertRaises(FrameDecodeError):capture.read()
    def test_source_timeout_is_reported_as_unavailable_not_corrupt(self):
        capture=StrictCapture.__new__(StrictCapture);capture.av=av;capture.opened=True;capture.rejected_frames=0;capture.waiting_keyframe=False;capture.pending=[]
        def packets():raise av.error.TimeoutError(110,'test-only timeout');yield
        capture.packets=packets()
        with self.assertRaises(SourceUnavailableError):capture.read()
        self.assertEqual(capture.rejected_frames,0)
    def test_concealed_pixels_cannot_continue_after_decoder_backlog(self):
        capture=StrictCapture.__new__(StrictCapture);capture.av=av;capture.opened=True;capture.width=96;capture.height=64;capture.rejected_frames=0;capture.waiting_keyframe=False;capture.anchor=(time.monotonic()-10,0)
        class Picture:
            is_corrupt=False;width=96;height=64;time=1.
            def to_ndarray(self,**kwargs):return np.zeros((64,96,3),np.uint8)
        capture.pending=[Picture()]
        with self.assertRaises(SourceUnavailableError):capture.read()
        self.assertGreater(capture.relative_lag_ms,8000)
    def test_async_native_error_rejects_pending_picture(self):
        capture=StrictCapture.__new__(StrictCapture);capture.av=av;capture.opened=True;capture.rejected_frames=0;capture.waiting_keyframe=False;capture.logs=[(av.logging.ERROR,'h264','test error')]
        capture.pending=[object()]
        with self.assertRaises(FrameDecodeError):capture.read()

if __name__=='__main__':unittest.main()

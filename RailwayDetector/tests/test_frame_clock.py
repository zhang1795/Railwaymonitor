import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from frame_clock import FrameClock, parse_start, timestamp, SHANGHAI

class ClockTests(unittest.TestCase):
    def test_java_nanosecond_control_timestamp_on_python38(self):
        parsed=parse_start('2026-11-10T04:08:04.422771448Z')
        self.assertEqual(parsed.microsecond,422771)
    def test_timezone_and_midnight(self):
        start = parse_start('2026-10-15T15:00:00Z')
        self.assertEqual(start.astimezone(SHANGHAI).hour,23)
        self.assertEqual((start+timedelta(hours=2)).astimezone(SHANGHAI).day,16)
        self.assertEqual(parse_start('2026-10-15 15:00:00',legacy=True), start)
        with self.assertRaises(ValueError): parse_start('2026-10-15 15:00:00')
        with self.assertRaises(ValueError): timestamp(datetime(2026,10,15))

    def test_file_time_is_independent_of_processing_time(self):
        start = parse_start('2026-10-15T15:00:00Z')
        clock = FrameClock(start,'sample.mp4',25)
        clock.at(0,0,start)
        result,source = clock.at(250,10000,start+timedelta(hours=1))
        self.assertEqual((result-start).total_seconds(),10)
        self.assertEqual(source,'media_time')

    def test_invalid_pts_uses_frame_index_and_fps(self):
        start = parse_start('2026-10-15T15:00:00Z')
        clock = FrameClock(start,'sample.mp4',25)
        clock.at(0,0,start)
        result,_ = clock.at(250,0,start)
        self.assertEqual((result-start).total_seconds(),10)

    def test_live_uses_received_time(self):
        start = parse_start('2026-10-15T15:00:00Z')
        received = start+timedelta(seconds=8)
        self.assertEqual(FrameClock(start,'rtsp://camera',25).at(0,0,received),
                         (received,'received_at'))

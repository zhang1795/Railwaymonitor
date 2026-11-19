"""Timezone-aware timestamps; processing latency is not media time."""
from datetime import datetime, timezone, timedelta
import math
import re
from urllib.parse import urlsplit

UTC = timezone.utc
SHANGHAI = timezone(timedelta(hours=8))

def parse_start(value, legacy=False):
    if not value:
        raise ValueError('startTime is required')
    source = str(value).replace('Z','+00:00')
    # Python 3.8 accepts 3/6 fractional digits; Java Instant may emit 9.
    # Normalize to microseconds without changing the timezone or wall time.
    source = re.sub(r'\.(\d{1,9})(?=(?:[+-]\d{2}:\d{2})?$)',
                    lambda match: '.'+(match.group(1)+'000000')[:6], source)
    parsed = datetime.fromisoformat(source)
    if parsed.tzinfo is None:
        if not legacy:
            raise ValueError('startTime must include a timezone')
        # Historical browser code stripped Z from toISOString(), which was UTC.
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

def timestamp(value):
    if value.tzinfo is None:
        raise ValueError('naive timestamp')
    return value.astimezone(UTC).isoformat(timespec='milliseconds')

class FrameClock:
    def __init__(self, start, source, fps):
        self.start = start
        self.live = urlsplit(str(source)).scheme.lower() in ('rtsp','rtsps','rtmp','http','https')
        self.fps = fps if math.isfinite(fps) and fps > 0 else 25.
        self.first_pts = None
        self.last_pts = None
        self.pts_valid = True

    def at(self, index, pts_ms, received):
        if self.live:
            return received, 'received_at'
        seconds = index/self.fps
        valid = math.isfinite(pts_ms) and pts_ms >= 0
        if self.pts_valid and valid:
            if self.first_pts is None:
                self.first_pts = pts_ms
            if self.last_pts is not None and pts_ms <= self.last_pts:
                self.pts_valid = False
            else:
                seconds = (pts_ms-self.first_pts)/1000.
                self.last_pts = pts_ms
        else:
            self.pts_valid = False
        return self.start+timedelta(seconds=seconds), 'media_time'

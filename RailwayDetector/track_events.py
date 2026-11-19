"""Per-track self-contained snapshots, independent of recording and networking."""
import json
import time
import uuid
from frame_clock import timestamp

CLASS_NAMES = ['Railway collision avoidance facilities', 'balloon', 'cow', 'flood',
               'huapo', 'illegal construction', 'kite', 'luoshi', 'nest', 'placard',
               'pothole', 'trash', 'worker']
CLASS_LABELS = ['防撞设备', '气球', '牛', '水害', '滑坡', '违规建筑', '风筝',
                '落石', '鸟巢', '广告牌', '坑洞', '垃圾', '工人']


class TrackEvents:
    def __init__(self, message, session_id, sink, clock=time.monotonic, interval=1., on_snapshot=None):
        self.message, self.session_id, self.sink = message, session_id, sink
        self.clock, self.interval = clock, interval
        self.tracks = {}
        self.on_snapshot = on_snapshot

    def _send(self, track, state, processed_at, reason=''):
        track['sequence'] += 1
        event = {k:v for k,v in track.items() if not k.startswith('_')}
        event.update(protocolVersion=4, eventId=uuid.uuid4().hex,
                     workerId=self.message.get('workerId', 'detector-1'),
                     cameraId=str(self.message['videoId']), sessionId=self.session_id,
                     generation=int(self.message.get('generation', 0)), state=state,
                     processedAt=timestamp(processed_at), reason=reason)
        # A successful call means durable handoff in production, not network IO.
        self.sink(json.dumps(event, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
        if self.on_snapshot is not None and state=='ACTIVE':
            try:
                self.on_snapshot(event)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Evidence unavailable; metadata remains durable')
        track['_sent_at'] = self.clock()
        track['_last_class'] = track['classId']
        track['_state'] = state

    def update(self, results, alive_ids, frame_time, time_source, processed_at, shape, raw_detections=()):
        for result in results:
            x1,y1,x2,y2 = result.bbox
            box=[max(0.,min(float(shape[1]),float(x1))),max(0.,min(float(shape[0]),float(y1))),
                 max(0.,min(float(shape[1]),float(x2))),max(0.,min(float(shape[0]),float(y2)))]
            if box[2]<=box[0] or box[3]<=box[1]:
                continue
            key = str(result.track_id)
            if key not in self.tracks:
                if len(self.tracks) >= 600:
                    raise RuntimeError('active track event capacity reached')
                self.tracks[key] = dict(trackId=key, sequence=0,
                    firstSeen=timestamp(frame_time), lastSeen=timestamp(frame_time),
                    classEvidence={}, _sent_at=float('-inf'), _last_class=None)
            track = self.tracks[key]
            track.pop('missingSince',None)
            track.update(lastSeen=timestamp(frame_time), observedThrough=timestamp(frame_time), timeSource=time_source,
                         classId=int(result.class_id), className=result.class_name,
                         confidence=float(result.confidence),
                         bbox=box,
                         frameWidth=int(shape[1]), frameHeight=int(shape[0]))
            evidence = track['classEvidence'].setdefault(str(result.class_id), {'count':0, 'maxScore':0.})
            evidence['count'] += 1
            evidence['maxScore'] = max(evidence['maxScore'], result.confidence)
            if track.get('_state')!='ACTIVE' or track['_last_class'] != result.class_id or self.clock()-track['_sent_at'] >= self.interval:
                self._send(track, 'ACTIVE', processed_at)
        matched = {str(result.track_id) for result in results}
        for key in set(self.tracks)-matched:
            track=self.tracks[key]
            track.setdefault('missingSince',timestamp(frame_time))
            track['observedThrough']=timestamp(frame_time)
            if key in {str(value) for value in alive_ids} and (track.get('_state')!='MISSING' or self.clock()-track['_sent_at']>=self.interval):
                self._send(track,'MISSING',processed_at,'observation_missing')
        for key in set(self.tracks)-{str(value) for value in alive_ids}:
            track = self.tracks[key]
            from frame_clock import parse_start
            if (frame_time-parse_start(track['missingSince'])).total_seconds()<float(self.message.get('trackGraceSeconds',3)):
                if track.get('_state')!='MISSING':self._send(track,'MISSING',processed_at,'observation_missing')
                continue
            def overlaps(detection):
                a,b=track['bbox'],detection.bbox
                area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area
                return detection.class_id==track['classId'] and union>0 and area/union>=.3
            uncertain=any(overlaps(detection) for detection in raw_detections)
            self._send(track, 'INTERRUPTED' if uncertain else 'ENDED', processed_at,
                       'identity_uncertain' if uncertain else 'confirmed_absence')
            del self.tracks[key]

    def finish(self, processed_at, interrupted=False):
        for key in list(self.tracks):
            self._send(self.tracks[key], 'INTERRUPTED' if interrupted else 'ENDED',
                       processed_at, 'task_failed' if interrupted else 'task_stopped')
            del self.tracks[key]

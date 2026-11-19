"""No-network probe: disconnecting viewer A removes viewer B's camera task."""
import contextlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'web-flask'))
import app


class Stream:
    stopped = False

    def stop(self):
        self.stopped = True


if __name__ == '__main__':
    # start_stream replaces the camera-keyed task but leaves camera_id in the
    # previous viewer's ws_tasks. Construct that exact reachable state.
    new_stream = Stream()
    app.stream_tasks[1] = {'stream': new_stream, 'ws_id': 'viewer-b', 'status': 'running'}
    app.ws_tasks.update({'viewer-a': {1}, 'viewer-b': {1}})
    with contextlib.redirect_stdout(io.StringIO()):
        app.cleanup_ws_tasks('viewer-a')
    report = {'viewer_b_stream_stopped_by_viewer_a_cleanup': new_stream.stopped,
              'viewer_b_task_removed': 1 not in app.stream_tasks}
    assert all(report.values())
    print(json.dumps(report, indent=2))

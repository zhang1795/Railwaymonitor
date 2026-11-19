"""Inspect the existing local validation deployment without modifying business data.

Only authentication / CSRF / logout requests are POSTed. Credentials and cookies
are kept in memory; the saved evidence excludes source URLs and personal data.
"""
import datetime
import http.cookiejar
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
BASE = 'http://127.0.0.1:18080/api'
ORIGIN = 'http://localhost:3000'


def main():
    credentials = json.loads((ROOT / 'workspace/runtime/p0-rollout/login-credentials.json').read_text())
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, body=None, csrf=None):
        headers = {'Origin': ORIGIN}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if csrf:
            headers[csrf['headerName']] = csrf['token']
        req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with opener.open(req, timeout=15) as response:
            result = json.load(response)
        if result['code'] not in (0, 200):
            raise RuntimeError('Read-only audit request rejected: ' + path)
        return result['data']

    csrf = request('/auth/csrf')
    request('/user/login', {key: credentials[key] for key in ('username', 'password')}, csrf)
    try:
        cameras = request('/camera/page?current=1&size=100')
        tasks = request('/monitoring')
        events = request('/Abnormal-event/page?current=1&size=5')
        detail = request('/Abnormal-event/' + str(events['records'][0]['id'])) if events['records'] else {}
        overview = request('/statistics/overview')
        event_stats = request('/statistics/Abnormal-event')
        device_stats = request('/statistics/device-status')
        report = {
            'checkedAt': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
            'businessWrites': 0,
            'cameras': {'total': cameras['total'], 'sample': [
                {key: row.get(key) for key in ('id', 'status')} | {'hasCoordinates': row.get('longitude') is not None and row.get('latitude') is not None}
                for row in cameras['records']
            ]},
            'monitoring': [{key: row.get(key) for key in ('camera_id', 'enabled', 'state', 'last_status_at')}
                           | {'hasError': bool(row.get('error'))} for row in tasks],
            'events': {'total': events['total'], 'samples': [
                {key: row.get(key) for key in ('id', 'cameraId', 'type', 'detectedType', 'confidence', 'detectionState', 'status')}
                | {'hasImage': bool(row.get('imageUrl')), 'hasDescription': bool(row.get('description'))}
                for row in events['records']
            ]},
            'eventDetailFields': sorted(detail),
            'statisticsResponseShapes': {
                'overview': {key: type(value).__name__ for key, value in overview.items()},
                'event': {key: type(value).__name__ for key, value in event_stats.items()},
                'device': {key: type(value).__name__ for key, value in device_stats.items()},
            },
        }
        destination = Path(__file__).with_name('read-only-api.json')
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        csrf = request('/auth/csrf')
        request('/user/logout', {}, csrf)


if __name__ == '__main__':
    main()

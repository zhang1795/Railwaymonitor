// Executes the actual monitor aggregation function with mocked IO and timers.
// These probes document defects; their assertions are not acceptance criteria.
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const root = path.resolve(__dirname, '../../..')
const ts = require(path.join(root, 'web-vue/node_modules/typescript'))
const source = fs.readFileSync(path.join(root, 'web-vue/src/views/monitor/index.vue'), 'utf8')
const begin = source.indexOf('const savedObjectIds:')
const end = source.indexOf('\nonMounted(', begin)
assert(begin >= 0 && end > begin)
const code = ts.transpileModule(source.slice(begin, end) +
  '\nreturn { handleDetectionData, savedObjectIds, globalAggregateCache };', {
  compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText

function fixture(fail = false) {
  const timers = new Map(), requests = []
  let next = 0
  const api = new Function('cameras', 'createAbnormalEvent', 'ElMessage', 'console',
    'setTimeout', 'clearTimeout', code)(
    { value: [{ id: 1, location: 'audit-location' }] },
    body => {
      requests.push(body)
      // Attach a handler here to keep the isolated probe quiet. The actual
      // caller neither awaits the result nor retries the failure.
      const pending = fail ? Promise.reject(new Error('audit HTTP failure')) : new Promise(() => {})
      pending.catch(() => {})
      return pending
    }, { warning() {} }, { log() {}, warn() {}, error() {} },
    callback => { timers.set(++next, callback); return next },
    id => timers.delete(id))
  return { ...api, requests, timers, flush() {
    const pending = [...timers.values()]
    timers.clear()
    pending.forEach(fn => fn())
  } }
}

function message(changes = {}) {
  return { videoId: '1', sessionId: 'audit-session', eventId: 'audit-session:1',
    startTime: '2026-11-10T01:00:00Z', endTime: '2026-11-10T01:00:01Z',
    videoFileUrl: null,
    result: [{ objectID: 'audit-session:1', objectDetect: '工人', score: .3,
      time: '2026-11-10T01:00:01Z', position: { x1: 1, y1: 1, x2: 10, y2: 10 } }],
    ...changes }
}

const category = fixture()
category.handleDetectionData(message())
category.handleDetectionData(message({ eventId: 'audit-session:2',
  result: [{ ...message().result[0], objectDetect: '牛', score: .95 }] }))
category.flush()
assert.equal(category.requests[0].type, '工人')
assert.equal(category.requests[0].level, 2)
assert.match(category.requests[0].description, /95\.0%/)

const failure = fixture(true)
failure.handleDetectionData(message())
failure.flush()
const markedBeforeSuccess = failure.savedObjectIds['1'].has('audit-session:1')
failure.handleDetectionData(message())
failure.flush()
assert(markedBeforeSuccess)
assert.equal(failure.requests.length, 1)

const continuous = fixture()
for (let i = 0; i < 300; i++) continuous.handleDetectionData(message({ eventId: `s:${i}` }))
assert.equal(continuous.requests.length, 0)
assert.equal(continuous.timers.size, 1)

const a = fixture(), b = fixture()
a.handleDetectionData(message()); b.handleDetectionData(message()); a.flush(); b.flush()
assert.equal(a.requests.length + b.requests.length, 2)

const invalid = fixture()
invalid.handleDetectionData(message({ result: [{ ...message().result[0], score: null }] }))
invalid.flush()
assert.equal(invalid.requests.length, 1)

console.log(JSON.stringify({
  category_score_mix: { stored_type: category.requests[0].type,
    stored_level: category.requests[0].level, score_text: '95.0% from 牛' },
  failed_http: { marked_saved_before_success: markedBeforeSuccess,
    request_count_after_same_target_redelivery: failure.requests.length },
  continuous_messages_without_quiet_period: { input: 300,
    requests_before_timer_fires: continuous.requests.length, pending_timer_count: continuous.timers.size },
  independent_pages_same_event: { create_requests: a.requests.length + b.requests.length },
  invalid_null_score: { create_requests: invalid.requests.length },
  stored_event_time_is_browser_now: category.requests[0].eventTime !== message().result[0].time,
}, null, 2))

// Audit reproductions of existing defects, not acceptance tests for fixed behavior.
// Runs production SFC scripts / WebSocket client with in-memory services only.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const root = path.resolve(__dirname, '../../..')
const localRequire = createRequire(path.join(root, 'web-vue/package.json'))
const ts = localRequire('typescript')
const vue = localRequire('vue')
const quiet = { log() {}, error() {}, warn() {} }

function clock() {
  let now = 0, id = 0
  const jobs = new Map()
  const add = (fn, ms, repeat) => { jobs.set(++id, { fn, due: now + ms, ms, repeat }); return id }
  return {
    jobs,
    setTimeout: (fn, ms) => add(fn, ms, false),
    setInterval: (fn, ms) => add(fn, ms, true),
    clearTimeout: key => jobs.delete(key),
    clearInterval: key => jobs.delete(key),
    async advance(ms) {
      const end = now + ms
      for (;;) {
        const next = [...jobs.entries()].filter(([, v]) => v.due <= end).sort((a, b) => a[1].due - b[1].due)[0]
        if (!next) break
        const [key, job] = next; now = job.due
        if (job.repeat) job.due += job.ms; else jobs.delete(key)
        await job.fn()
      }
      now = end
    },
  }
}
const flush = () => new Promise(resolve => setImmediate(resolve))

function component(relative, names, extras = {}) {
  const mounted = [], unmounted = [], messages = [], sends = [], writes = []
  const timer = clock()
  const message = Object.assign(value => messages.push(value), Object.fromEntries(
    ['success', 'error', 'warning', 'info'].map(kind => [kind, value => messages.push({ kind, value })])))
  const transport = {
    connected: true, resetCount: 0,
    isConnected() { return this.connected },
    send(value) { sends.push(value) },
    resetConnectionState() { this.resetCount++ },
    addMessageHandler() {}, removeMessageHandler() {}, close() {}, connect() {},
  }
  const modules = {
    vue: { ...vue, onMounted: fn => mounted.push(fn), onBeforeUnmount: fn => unmounted.push(fn), onUnmounted: fn => unmounted.push(fn) },
    'vue-router': { useRouter: () => ({ push() {} }) },
    'element-plus': { ElMessage: message, ElMessageBox: { confirm: async () => {}, alert: async () => {} } },
    '@/stores/user': { useUserStore: () => ({ userInfo: { id: 1, role: 1 } }) },
    '@/utils/websocket': { __esModule: true, default: transport },
    '@/utils/format': { formatDateTime: value => value, formatDeviceStatus: String, formatAbnormalLevel: String, formatStatus: String },
    '@/utils/validate': { validateIP: () => true, validateRTSP: () => true },
    '@element-plus/icons-vue': {},
    '@/api/camera': { getCameraList: async () => ({ records: [], total: 0 }), createCamera: async value => writes.push(value) },
    '@/api/monitoring': { getMonitoring: async () => [], setMonitoring: async (...value) => writes.push(value) },
    '@amap/amap-jsapi-loader': { __esModule: true, default: { load: async () => { throw Error('Unexpected external map load') } } },
    ...extras.modules,
  }
  const source = fs.readFileSync(path.join(root, 'web-vue/src', relative), 'utf8').match(/<script setup lang="ts">([\s\S]*?)<\/script>/)[1].replace(/import\.meta\.env/g, 'testEnv')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText
  class Image {
    width = 640; height = 480
    set src(value) { this.onload?.() }
  }
  const exposed = new Function('require', 'exports', 'window', 'console', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'defineProps', 'defineEmits', 'defineExpose', 'testEnv', 'Image', output + '\nreturn {' + names.join(',') + '};')(
    name => { if (name.endsWith('.vue')) return {}; assert(name in modules, 'Unexpected dependency: ' + name); return modules[name] },
    {}, { ...timer }, quiet, timer.setTimeout, timer.clearTimeout, timer.setInterval, timer.clearInterval,
    () => extras.props || {}, () => () => {}, () => {}, extras.env || {}, Image)
  return { ...exposed, transport, messages, sends, writes, timer,
    async mount() { for (const fn of mounted) await fn(); await flush() },
    unmount() { unmounted.forEach(fn => fn()) },
  }
}

function monitor(extras) {
  return component('views/monitor/index.vue', ['cameras', 'activeCamera', 'monitoringEnabled', 'detectorStates', 'handleCameraSelect', 'toggleMonitoring', 'refreshDetectionState'], extras)
}

test('F01: offline camera and disconnected preview prevent selecting a running task for stopping', async () => {
  const page = monitor({ modules: { '@/api/monitoring': { getMonitoring: async () => [{ camera_id: 1, enabled: true, state: 'RUNNING' }], setMonitoring: async () => assert.fail('No selectable task') } } })
  await page.refreshDetectionState()
  assert.equal(page.monitoringEnabled.value[1], true)
  const camera = { id: 1, status: 0 }
  page.handleCameraSelect(camera)
  assert.equal(page.activeCamera.value, undefined)
  camera.status = 1; page.transport.connected = false
  page.handleCameraSelect(camera)
  assert.equal(page.activeCamera.value, undefined)
  await page.toggleMonitoring()
  assert.equal(page.transport.resetCount, 1)
})

test('F02: failed status polls leave RUNNING visible without checking sample age', async () => {
  let offline = false
  const page = monitor({ modules: { '@/api/monitoring': { getMonitoring: async () => {
    if (offline) throw Error('network unavailable')
    return [{ camera_id: 1, enabled: true, state: 'RUNNING', last_status_at: '2000-01-01T00:00:00', error: '' }]
  } } } })
  await page.refreshDetectionState()
  assert.equal(page.detectorStates.value[1], '检测中')
  offline = true
  for (let i = 0; i < 10; i++) await page.refreshDetectionState()
  assert.equal(page.detectorStates.value[1], '检测中')
  assert.equal(page.monitoringEnabled.value[1], true)
  assert.equal(page.messages.length, 0)
})

test('F03: after the first frame, missing frames leave the old canvas and online state indefinitely; retry is a no-op when disconnected', async () => {
  const camera = vue.reactive({ id: 1, name: 'test-camera', status: 1 })
  const player = component('components/VideoPlayer/index.vue', ['canvas', 'handleMessage', 'isLoading', 'hasConnectionError', 'retryConnection'], { props: { camera, isActive: true } })
  let drawn = 0, cleared = 0
  const context = { fillRect() { cleared++ }, clearRect() { cleared++ }, drawImage() { drawn++ } }
  player.canvas.value = vue.markRaw({ width: 640, height: 480, getContext: () => context })
  await player.mount()
  player.handleMessage({ type: 'video_frame', data: { cameraId: 1, frame: 'data:image/jpeg;base64,test-only' } })
  player.handleMessage({ type: 'stream_ready', data: { cameraId: 1 } })
  assert.equal(drawn, 1)
  const before = { sends: player.sends.length, cleared }
  player.transport.connected = false
  await player.timer.advance(120000)
  assert.equal(cleared, before.cleared)
  assert.equal(player.isLoading.value, false)
  assert.equal(player.hasConnectionError.value, false)
  assert.equal(camera.status, 1)
  player.retryConnection()
  assert.equal(player.sends.length, before.sends)
  assert.equal(player.transport.resetCount, 0)
  player.unmount()
})

test('F03: the production WebSocket connection flag does not invalidate a Vue render effect', async () => {
  const sockets = [], timer = clock()
  class Socket {
    static OPEN = 1; static CONNECTING = 0
    constructor() { this.readyState = 0; sockets.push(this) }
    send() {}
    close() { this.readyState = 3 }
  }
  const source = fs.readFileSync(path.join(root, 'web-vue/src/utils/websocket.ts'), 'utf8').replace(/import\.meta\.env/g, 'testEnv')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText
  const exports = {}
  new Function('exports', 'require', 'window', 'WebSocket', 'console', 'testEnv', 'setInterval', 'clearInterval', output)(
    exports, () => ({ __esModule: true, default: { post: async () => ({ grant: 'test-only' }) } }),
    { ...timer, location: { protocol: 'http:', host: 'localhost:3000' } }, Socket, quiet, {}, timer.setInterval, timer.clearInterval)
  const client = exports.default, observations = []
  const effect = vue.effect(() => observations.push(client.isConnected()))
  client.connect(); const socket = sockets[0]; socket.readyState = 1; await socket.onopen()
  socket.onmessage({ data: JSON.stringify({ type: 'authenticated', data: { cameraId: 0 } }) })
  assert.equal(client.isConnected(), true)
  assert.deepEqual(observations, [false])
  socket.readyState = 3; socket.onclose({ code: 1006, wasClean: false })
  assert.equal(client.isConnected(), false)
  assert.deepEqual(observations, [false])
  vue.stop(effect); client.close()
})

test('F04: a new server alarm is not fetched by an already-open abnormal-events page', async () => {
  let rows = [{ id: 1, status: 0 }], calls = 0
  const page = component('views/Abnormal/index.vue', ['list', 'getList'], { modules: {
    '@/api/Abnormal': { getAbnormalEventList: async () => { calls++; return { records: rows, total: rows.length } } },
  } })
  await page.mount()
  assert.equal(calls, 1)
  rows = [{ id: 2, status: 0 }, ...rows]
  await page.timer.advance(60000); await flush()
  assert.equal(calls, 1)
  assert.deepEqual(page.list.value.map(row => row.id), [1])
  await page.getList()
  assert.deepEqual(page.list.value.map(row => row.id), [2, 1])
})

test('F06: without map credentials the map produces no coordinates and camera creation has no fallback', async () => {
  const map = component('components/Map/index.vue', ['initMap'])
  await map.mount()
  assert(map.messages.some(item => item.value?.includes('未配置高德地图密钥')))
  const page = component('views/camera/index.vue', ['form', 'formRef', 'handleCreate', 'submitForm'])
  page.handleCreate()
  Object.assign(page.form, { name: 'test', location: 'test', ipAddress: '127.0.0.1', rtspUrl: 'rtsp://127.0.0.1/test' })
  page.formRef.value = { validate: async () => true }
  await page.submitForm()
  assert.equal(page.writes.length, 0)
  assert(page.messages.some(item => item.value === '请在地图上选择安装位置'))
})

test('F06: even with credentials, a map SDK failure has no initialization recovery path', async () => {
  const map = component('components/Map/index.vue', ['initMap'], {
    env: { VITE_AMAP_KEY: 'test-only', VITE_AMAP_SECURITY_CODE: 'test-only' },
    modules: { '@amap/amap-jsapi-loader': { __esModule: true, default: { load: async () => { throw Error('simulated SDK network failure') } } } },
  })
  await assert.rejects(map.initMap(), /simulated SDK network failure/)
})

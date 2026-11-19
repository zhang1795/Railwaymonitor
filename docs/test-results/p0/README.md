# P0 回归证据（2026-11-10）

汇总见 [实现与验证记录](../../p0-implementation-results.md)。本目录只保存脱敏结果，不包含服务密钥、证书私钥、业务数据库导出和测试会话令牌。日志为相关命令输出的结尾或测试摘要，非完整日志。

## 已保存结果

- `detector-tests.txt`：58 项检测组件测试通过。
- `flask-tests.txt`：5 项预览授权/隔离测试通过。
- `frontend-preview-tests.txt`：2 项授权 WS 测试通过。
- `frontend-legacy-tests.txt`：11 项旧适配器兼容测试通过，旧适配器已退出生产监控路径。
- `backend-h2-tests.txt`：21 项通过，未配置的 MQTT 项明确跳过。
- `backend-tests.txt`：21 项真实 MySQL 回归与 1 项 TLS MQTT 故障集成通过，jar 打包成功。
- `mqtt-recovery.json`：零浏览器、Broker 重启、工作进程强杀、新会话、最终待发清空。
- `broker-security.json`：6 类未授权/证书错误拒绝。
- `backend-restart.json`：最终 jar、真实 MySQL/TLS MQTT，后端进程重启后恢复持久配置，租约内保持同会话且不重复。
- `live-preview.json`：真实 RTSP/JPEG、HTTP Session/CSRF、忽略客户端视频源与退出吊销流。
- `frontend-build.txt`：vue-tsc 与 Vite 构建输出结尾。
- `local-deployment.json`：后续本机实际切换，真实 YOLO/RTSP/已迁移业务库的功能验收；新增样例明确标记，原历史记录保留。

MQTT 使用合成轨迹，未加载 YOLO；实际预览使用本地样例视频经临时 MediaMTX 发布。不能用这些结果代替真实场景精度、并发容量或长期稳定性指标。

## 无外部服务的复跑

在根目录执行；运行环境路径沿用本机配置，Node/npm 需要先加入 PATH：

```bash
PYTHONDONTWRITEBYTECODE=1 workspace/runtime/detector-env/bin/python -m unittest discover -s RailwayDetector/tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 workspace/runtime/flask-venv/bin/python -m unittest discover -s web-flask/tests -p 'test_*.py'
node web-vue/tests/secure-preview.test.cjs
node web-vue/tests/detector-tasks.test.cjs
```

在 `web-springboot` 内执行（普通运行使用 H2，不连接业务库）：

```bash
env -u DEBUG JAVA_HOME=../workspace/runtime/jdk17/usr/lib/jvm/java-17-openjdk-amd64 \
  ../../apache-maven-3.9.9/bin/mvn -B -o \
  -gs ../deploy/maven-settings.xml -s ../deploy/maven-settings.xml \
  -Dmaven.repo.local=../workspace/runtime/m2 test
```

在 `web-vue` 内执行 `npm run build`。

## 真实服务的复跑契约

只使用新建且可丢弃的隔离测试环境。**测试会清空测试表，绝对不能设置业务库 URL。** 本轮数据库为独立 mysqld 的 `127.0.0.1:13317/railway_p0_test`；测试不执行既有业务库迁移。

1. 准备 EMQX 5.8.8 隔离实例，按部署配置启用 TLS、账号和 ACL；用户名固定 `detector-1` / `railway-backend`，凭据为随机值。准备可信 CA，证书 SAN 匹配主机名。用 `prepare_p0_broker.py --provision` 配置测试实例，不连接已有部署。
2. 准备空的 MySQL 测试库。`P0IntegrationTest` 设置 `P0_TEST_DB_URL` 后使用真实 MySQL，测试用户为 root、空口令，仅适用于隔离测试实例；SQL 初始化执行 `base-schema.sql` 和实际增量迁移。每次重新执行初始化前重建这个临时库，不能重跑到已迁移业务库。重建测试数据库时也要使用新的临时工作节点目录，避免混入旧会话/控制代次；实际故障恢复应保全已有 outbox，不能照此清空生产状态。
3. 设置 `P0_MQTT_URI=ssl://localhost:18884`、`P0_MQTT_PERSISTENCE` 为私有临时目录，并提供 `MQTT_BACKEND_USERNAME/PASSWORD`、`MQTT_USERNAME/PASSWORD`、`MQTT_HOST/PORT`、`MQTT_CA_FILE`。前述 Maven 命令将启用 `P0MqttIntegrationTest`。该项自身使用独立 H2 业务库；同次运行的 21 项回归使用上一步 MySQL，区分两者。
4. 仅当测试容器名称确为 `railway-p0-test` 时设置 `P0_MANAGE_TEST_BROKER=true`；该开关会停止/启动这个容器。未设置时不执行 Broker 重启，不能声称验证过重启。
5. Broker 负向验证：根目录运行 `workspace/runtime/detector-env/bin/python RailwayDetector/tests/check_broker_security.py`，使用测试 TLS 端口 18884 与上述凭据。
6. 真实预览：准备临时 MediaMTX 和样例 RTSP，将测试摄像头 1 指向该源，启动最终 jar 与 Flask。设置 `P0_HTTP_URL`、`P0_WS_URL`、`P0_TEST_PASSWORD`，运行 `node web-vue/tests/live-preview-smoke.cjs`；测试 Origin 为 `http://127.0.0.1:3000`，需在测试网关白名单中。该项会登录测试管理员并退出登录。

后端重启验收额外使用最终 jar 启停两次、同一持久 MySQL、同一工作进程：首次启用→已有事件→重启后重新登录→检查 enabled/session 保留→继续收到事件→同会话告警仍为 1→显式停用并等待 STOPPED。它是本轮隔离进程验收记录；目前尚未整理为通用自动部署脚本。

所有临时服务在验收后清理，已有业务服务保持运行。原审查的缺陷复现脚本保留历史证据用途，不属于修复后的正向回归。

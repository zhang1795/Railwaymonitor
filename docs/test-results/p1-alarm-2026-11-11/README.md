# P1 第一批脱敏测试证据

对应 [实现报告](../../p1-alarm-implementation-results-2026-11-11.md)。包含源码/隔离验收，以及用户明确同意后完成的本机迁移、切换与实际业务只读验证。首次发布命令曾被自动审批审查拒绝，没有绕过限制。

| 文件 | 内容 |
| --- | --- |
| `detector.txt` | 最终 Python 73 项回归 |
| `backend-h2.txt` | H2 77 项业务回归 |
| `backend-mysql-mqtt.txt` | 同套 77 项真实 MySQL + 1 项 TLS MQTT 故障集成 |
| `frontend-*.txt` | 生产脚本 6+11+8+6，共 31 项；类型检查与 Vite 构建 |
| `deployment-tools.txt` | Java/Python 不可变发布工具 6 项 |
| `live-runtime.json` | 实际等待 60 秒、数据库中断、后端强杀、另行真实 YOLO/RTSP/双预览/截图 |
| `migration.json` | 隔离库连续重跑两次增量迁移，计数保持 |
| `screenshot-verification.json` | 实际授权读取图片的尺寸、字节数、校验和与查看记录，不含图片内容 |
| `releases.json` | 最终已固化运行包的哈希，不代表已运行 |
| `cleanup.json` | 隔离服务清理状态 |
| `deployment.json` | 本机实际切换后检查、恢复耗时与备份摘要，无凭据和业务图片 |
| `summary.json` | 总览与未完成项 |

完整私有日志在 `workspace/runtime/p1-alarm/` 和 `workspace/runtime/p0-reaudit/p1/`，本机备份与切换记录在 `workspace/runtime/p1-rollout/20261111-alarm/`，不提交服务密钥、私钥、Session、业务备份或样例图片。最终两处补强（截图队列权限、规则表单保存竞态）在隔离实链之后完成，对应组件回归和构建已重跑，随后在本机实际启用并验证截图。真实 60 秒测试是构造观测通过实际 MQTT/后端的运行测试，真实 YOLO 片段单独验证，不是现场精度或遮挡验收。

## 复跑

根目录，先准备现有 Python/Node 22 依赖：

```bash
workspace/runtime/detector-env/bin/python -m unittest discover -s RailwayDetector/tests
python3 -m unittest discover -s deploy/tests
node web-vue/tests/monitor-lifecycle.test.cjs
node web-vue/tests/secure-preview.test.cjs
node web-vue/tests/alarm-inbox.test.cjs
node web-vue/tests/risk-interaction.test.cjs
```

前端在 `web-vue` 执行 `npm run build`。后端使用项目既有 JDK17、Maven、本地依赖库和 `deploy/maven-settings.xml` 运行 `P0IntegrationTest`，移除继承的 `DEBUG`。H2 默认使用随机临时库，测试 schema 同时执行 P0、通知、P1 迁移；这些测试初始化脚本不能对业务库运行。

真实 MySQL/TLS MQTT 及 RTSP 组合沿用 [隔离环境复跑说明](../p0-reaudit-2026-11-10/README.md)。新建短目录，例如 `workspace/runtime/p0-reaudit/p1b`，由 `p0_test_environment.py prepare` 创建；只允许 13317 的 `railway_p0_test`，从私有 `services.env` 给 Maven 子进程提供测试配置，执行 `package` 后再运行：

```bash
python3 deploy/p0_live_acceptance.py --directory workspace/runtime/p0-reaudit/p1b
python3 deploy/p0_test_environment.py cleanup --directory workspace/runtime/p0-reaudit/p1b
```

运行组合会清理隔离库并注入隔离服务故障，不能替换为业务地址。本轮服务已清理，不可直接复用已标记 cleanedUp 的目录。缺少本地样例视频、真实权重或 Docker 时应明确失败。测试不重启业务服务；已读/处理操作只针对隔离测试事件。浏览器宿主不可用，前端脚本测试和实际 WebSocket 客户端连线不等于 DOM/视觉验收。

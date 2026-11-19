# P0 完整复验证据

主报告：[p0-revalidation-2026-11-10.md](../../p0-revalidation-2026-11-10.md)。本目录为脱敏摘要；密钥、私钥、业务数据导出、会话令牌及完整日志不提交。

## 结果文件

- `before-fix-failures.txt`：时间校验的 2 条失败、人工并发的 3 条失败（H2 和真实 MySQL），以及禁止字体下载时的冷启动失败。
- `backend-h2.txt`、`backend-mysql-mqtt.txt`、`backend-mysql-final.txt`：补修后的 50 项业务回归与独立 MQTT 故障验收。
- `mqtt-faults.json`：业务 ACK 丢失、Broker 重启/强杀、工作节点重启与最终积压状态。
- `broker-security.json`：11 类身份、ACL、TLS 负向验证。
- `live-runtime.json`：真实 MySQL 中断、后端强杀、空缓存真实模型、双观看连接与退出登录。
- `business-consistency.json`：业务库自动告警与轨迹快照的只读核对；不修写历史数据。
- `business-recovery.json`：本次升级中断及恢复事实，明确原会话未保留。
- `build-isolation.json`：构建后运行进程继续存活，运行副本与最终构建的业务类一致。
- `deployment-after.json`、`status-metric-samples.json`：清理测试资源后的运行状态，以及旧任务积压采样和当前 outbox 口径的差异。
- `*-tests.txt`、`detector-final.txt`、`frontend-*.txt`：组件测试及构建输出摘要。
- `summary.json`：总览；包含实际未覆盖的边界。

MySQL 故障注入期间的连接失败/Hikari 警告是预期现象；恢复以最终断言为准。字体下载异常及业务并发字段倒退是实际缺陷，修复前失败证据保留。旧运行包被覆盖造成的升级中断单独披露，不归入“未发生故障”。

## 复跑

先准备 Node 22、项目现有 JDK/Maven/Python 环境。根目录运行：

```bash
workspace/runtime/detector-env/bin/python -m unittest discover -s RailwayDetector/tests -p 'test_*.py'
workspace/runtime/flask-venv/bin/python -m unittest discover -s web-flask/tests -p 'test_*.py'
python3 -m unittest discover -s deploy/tests -p 'test_*.py'
node web-vue/tests/secure-preview.test.cjs
node web-vue/tests/monitor-lifecycle.test.cjs
```

在 `web-springboot` 执行已有离线 Maven 命令可运行 H2；`web-vue` 内执行 `npm run build`。实际浏览器点击不在这些测试中。

隔离故障测试使用新目录，例如 `workspace/runtime/p0-reaudit/new-run`：

```bash
python3 deploy/p0_test_environment.py prepare --directory workspace/runtime/p0-reaudit/new-run
```

该脚本创建 `railway-p0-test`、`railway-p0-preview` 和独立网络，MySQL 为 13317 / `railway_p0_test`，TLS MQTT 为 18884，RTSP 为 18554，私有环境写入该目录的 `services.env`。已有同名容器时拒绝替换。不得改为业务数据库地址；Java 测试也会拒绝不符合测试前缀的 URL。

用 Python 读取 `services.env` 更新子进程环境，移除继承的 `DEBUG`，设置项目 JDK17 的 `JAVA_HOME`，在 `web-springboot` 运行已有 Maven `package` 命令，会启用真实 MySQL 与 MQTT 测试。不要输出环境变量内容。新环境仅初始化一次；需要重建时先清理旧测试实例，再用新目录，不混用旧 outbox 与重建后的数据库。

随后执行：

```bash
python3 deploy/p0_live_acceptance.py --directory workspace/runtime/p0-reaudit/new-run
python3 deploy/p0_test_environment.py cleanup --directory workspace/runtime/p0-reaudit/new-run
```

运行验收会清空**隔离库**中的测试记录，并停止/启动隔离 MySQL、强杀隔离后端；它不重启业务服务。清理前校验容器 ID、标签、数据库 PID 与数据目录，仅删除本次记录的测试资源，证据文件保留。样例视频和可信权重必须事先存在，缺少时明确失败，不伪造通过。

Broker 额外负向检查用同一私有环境执行 `RailwayDetector/tests/check_broker_security.py`。人工并发调度钩子位于 `web-springboot/src/test`，不会进入运行 jar。构建与长驻进程使用不同的运行副本，防止复验再次覆盖正在运行的包。

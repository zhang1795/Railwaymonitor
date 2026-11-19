# 初步部署说明

当前部署采用“本机进程 + Docker 基础设施”：MySQL、Spring Boot、Vue、Flask 和算法进程在宿主机运行，EMQX 与 MediaMTX 使用 Docker。它适合第一阶段联调和代码学习，不等同于最终生产部署。

当前运行方式、实际端口及最新版本核对见 [当前部署状态](../docs/current-deployment.md)。本机前端入口为 3000，业务后端为 18080；不能将基础设施容器更新误认为业务代码已容器化。

## 启动前置条件

P0 版本更改了数据库结构、MQTT 服务身份、登录和预览协议。现有环境不能直接运行新脚本覆盖启动；先按 [P0 切换与回退](P0-ROLLOUT.md) 备份、执行一次增量迁移、设置管理员和 TLS/ACL。

前端 F01–F04 版本另需执行 `web-springboot/src/main/resources/db/frontend-notices-migration.sql`，已有 P0 环境不重跑旧 ALTER 迁移。该表仅保存个人已读状态，不修改告警处置结果。

当前 P1 告警源码另需 `web-springboot/src/main/resources/db/p1-alarm-migration.sql` 和独立截图服务配置，按 [P1 切换指南](P1-ALARM-ROLLOUT.md) 执行。该迁移可重复执行；新 jar 必须在迁移后启动，后端与检测进程需要配套更新。本机已于 2026-11-11 完成该次迁移与切换，过程和验证见本批报告。

从 `.env.example`、`.env.p0.example` 分别创建私有 `.env`、`.env.p0`，填写真实值并 `chmod 600`。`.env.p0` 的密钥占位符不能用于启动。依赖路径、模型、运行环境需自行准备；不要假设仓库携带本机环境。

完成准备后，本机联调可使用：

```bash
./deploy/start.sh                 # API、页面与预览，不加载模型
./deploy/start.sh --with-detector # 加载检测工作进程
./deploy/start.sh --with-detector --with-demo # 本机样例流，需已有 smoke-cow-short.mp4
./deploy/status.sh
./deploy/stop.sh
```

脚本使用 Vite 和 Gunicorn 预览网关。对外服务使用 HTTPS Nginx 静态页面及同源反向代理，参考 [nginx-p0.conf](nginx-p0.conf)。OS 自启动与生产容量验收另行落实。

## 服务地址

| 服务 | 默认地址/端口 | 作用 |
| --- | --- | --- |
| Vue 开发服务器 | `http://127.0.0.1:3000` | 本机联调；生产由 Nginx 提供 dist |
| Spring Boot | `http://127.0.0.1:8080/api` | Session/CSRF 保护的业务 API |
| Flask | `http://127.0.0.1:5000/api/health` | 授权预览，代理 `/stream/ws` |
| MySQL | `127.0.0.1:3307` | 业务数据与监测配置 |
| EMQX MQTT/TLS | `127.0.0.1:8883` | 工作节点与后端的服务消息 |
| EMQX 本地开发 MQTT | `127.0.0.1:1883` | 仅显式允许的环回明文开发 |
| EMQX Dashboard | `http://127.0.0.1:18083` | 私有管理界面 |
| MediaMTX RTSP | `rtsp://127.0.0.1:8554/流名称` | 本机媒体源；其它媒体端口也只绑定环回 |

浏览器不再连接 MQTT，8083 未开放。不要暴露初始种子账号，离线管理员引导方式见切换说明。远程工作节点需显式配置 TLS 发布地址及防火墙；媒体源跨主机发布需要额外配置认证与网络策略。

本机实际切换、端口调整、验收账号位置和样例摄像头见 [本机验收部署记录](../docs/p0-local-deployment.md)。如果 8080 被占用，保持 `SERVER_PORT`、`BACKEND_INTERNAL_URL`、`VITE_API_PROXY_TARGET` 三项地址一致。新项目网络默认使用 `railway-monitoring-p0`；旧网段与 VPN/代理重叠时，需要使用 `docker compose up -d --force-recreate` 将容器切到新网络，数据卷保持不变。

## 构建命令

后端：

```bash
cd web-springboot
env JAVA_HOME=../workspace/runtime/jdk17/usr/lib/jvm/java-17-openjdk-amd64 \
  ../../apache-maven-3.9.9/bin/mvn \
  -gs ../deploy/maven-settings.xml -s ../deploy/maven-settings.xml \
  -Dmaven.repo.local=../workspace/runtime/m2 clean package
```

前端：

```bash
cd web-vue
npm run build
```

Flask 最小依赖与完整算法依赖已经分离：`web-flask/requirements-runtime.txt` 只负责视频网关；`RailwayDetector/requirements.txt` 负责 YOLO 环境。

## 当前边界

P0 交付阻断的代码改动与隔离验证见 [实现与验证记录](../docs/p0-implementation-results.md)。此前第一阶段的“页面负责 MQTT 聚合与落库”路径已被替换。

- 检测元数据先持久化到 SQLite，后端事务提交后业务 ACK；浏览器只查询结果。没有页面也可监测和入库。
- 未配置规则仅记录待核验观察；配置后按区域/类别/当前分数与停留时间建立风险事件，短时有限续接，人工字段独立保留，错误数据进入拒绝记录。
- P1 提供持久截图与独立源录像登记、授权读取、30 天保留和 2 TB 应用预算；需后端/节点共享持久卷。站内持续/升级提醒、签名 Webhook 与阿里云短信待发/回执代码已接入，真实外部渠道尚未配置，不能声称短信已送达。详见 [本轮结果](../docs/p1-completion-results-2026-11-11.md)及[切换说明](P1-STABILITY-ROLLOUT.md)。
- 单后端、单检测工作节点；工作节点 ID 不能重复运行。CPU 样例推理速度不能替代真实多路吞吐与长期稳定性验收。
- 遮挡与模型精度、现场 ROI/阈值校准、合同容量、长时运行、关键元数据保留/归档及全新机器安装仍需独立验收。当前守护管理应用进程，OS 自启动和日志轮转模板需主机运维安装；本机网关已使用 Gunicorn，不再使用 Flask 开发服务器。

## 代码阅读顺序

1. `RailwayDetector/ui.py`、`track_events.py`：逐帧处理与轨迹快照。
2. `RailwayDetector/event_outbox.py`、`mqtt_service.py`：持久待发、业务确认、控制代次与会话恢复。
3. `web-springboot/src/main/java/com/example/detection`：后台监测、MQTT 接收、事务聚合。
4. `web-springboot/src/main/java/com/example/security`、`UserServiceImpl`：Session、CSRF、授权与预览凭证。
5. `web-flask/app.py`、`web-vue/src/utils/websocket.ts`：授权预览和连接隔离。
6. `web-vue/src/views/monitor/index.vue`：后台监测启停与独立的观看操作。

# 初步部署说明

当前部署采用“本机进程 + Docker 基础设施”：MySQL、Spring Boot、Vue、Flask 和算法进程在宿主机运行，EMQX 与 MediaMTX 使用 Docker。它适合第一阶段联调和代码学习，不等同于最终生产部署。

## 快速启动

运行基础系统（不加载 YOLO）：

```bash
./deploy/start.sh
```

运行完整系统（额外加载 CPU YOLO+SORT）：

```bash
./deploy/start.sh --with-detector
```

查看状态或停止：

```bash
./deploy/status.sh
./deploy/stop.sh
```

本机已经准备好 `deploy/.env`、MySQL 数据、JDK 17、Flask 虚拟环境和算法环境。迁移到新机器时，从 `deploy/.env.example` 创建 `.env`，并更换数据库密码。

## 服务地址

| 服务 | 地址/端口 | 作用 |
| --- | --- | --- |
| Vue | `http://服务器IP:3000` | 管理与监控页面 |
| Spring Boot | `http://127.0.0.1:8080/api` | 业务 API |
| Flask | `http://127.0.0.1:5000/api/health` | RTSP 到 WebSocket/JPEG 网关 |
| MySQL | `127.0.0.1:3307` | `railway_monitoring` 数据库 |
| EMQX MQTT | `1883` | 算法任务和告警消息 |
| EMQX WebSocket | `8083` | 浏览器 MQTT 连接 |
| EMQX Dashboard | `http://127.0.0.1:18083` | MQTT 管理界面 |
| MediaMTX RTSP | `rtsp://服务器IP:8554/流名称` | RTSP 发布与读取 |

开发数据中的页面账号为 `admin / 123456`，仅用于本地学习，正式部署前必须修改。EMQX 当前也按初步联调方式运行，正式上线前应启用 MQTT 认证并限制端口访问。

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

## 第一阶段边界

- 已跑通登录、摄像头 CRUD、异常事件、统计、RTSP 推拉流、Flask WebSocket 视频帧、MQTT 回环，以及 YOLO+SORT→MQTT→异常事件 API 的可回滚闭环。
- 文件服务和 MinIO 尚未启用，算法告警中的视频文件地址暂为“待上传”。
- Vue 与 Flask 当前使用开发服务器。生产化时应改为 Nginx 静态资源、Gunicorn/Geven 等 WebSocket 服务器、systemd/容器编排，以及完整的 TLS、认证、日志轮转和监控。
- 算法默认 CPU；当前样例单帧推理约 0.13–0.17 秒，适合功能验证，不代表实时多路吞吐。

## 建议的代码阅读顺序

1. `web-vue/src/views/monitor/index.vue`：页面如何同时驱动 WebSocket 与 MQTT。
2. `web-flask/app.py`、`web-flask/algo/utils.py`：RTSP 帧如何被读取并转成 WebSocket JPEG。
3. `RailwayDetector/ui.py`、`model_init.py`、`tracker.py`：视频任务、YOLO 推理、SORT 跟踪与告警聚合。
4. `web-springboot/controller` → `service/impl` → `mapper` → `entity`：业务 API 到 MySQL 的典型调用链。
5. `web-vue/src/views/monitor/index.vue` 中 `handleDetectionData`：告警去重、聚合并落库的关键业务逻辑。

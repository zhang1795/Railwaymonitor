# Railway Monitoring System

铁路沿线异常监测项目的本地可运行基线版本，包含管理前端、业务后端、视频流网关、目标检测程序及基础设施配置。

## 系统组成

- `web-vue`：Vue 3 管理与实时监控页面
- `web-springboot`：Spring Boot 业务 API 与 MySQL 数据访问
- `web-flask`：RTSP 拉流、OpenCV 帧处理与 WebSocket 推送
- `RailwayDetector`：YOLO + SORT 检测与跟踪程序
- `deploy`：MySQL、EMQX、MediaMTX 及本地服务启动脚本

## 当前基线

当前版本已经完成登录、摄像头管理、异常事件、统计、RTSP 推拉流、WebSocket 视频帧、MQTT 回环，以及检测结果落库等第一阶段联调。

本仓库不包含本地虚拟环境、Node.js 依赖、构建产物、模型权重、测试视频和真实环境变量。首次部署前需要自行准备这些运行资源，并根据 `deploy/.env.example` 创建 `deploy/.env`。

部署方式、服务端口、构建命令、当前限制和推荐代码阅读顺序参见 [部署说明](deploy/README.md)。

## 安全提示

仓库中的初始化数据仅用于本地学习和功能验证。部署到公网或生产环境前，必须更换默认账号和密码、启用 MQTT 认证，并配置 TLS、访问控制、日志轮转和服务守护。

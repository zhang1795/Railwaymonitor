# Railway Monitoring System

铁路沿线异常监测项目，包含管理前端、业务后端、视频预览网关、目标检测程序及基础设施配置。

## 系统组成

- `web-vue`：Vue 3 管理与实时监控页面
- `web-springboot`：Spring Boot 业务 API 与 MySQL 数据访问
- `web-flask`：RTSP 拉流、OpenCV 帧处理与 WebSocket 推送
- `RailwayDetector`：YOLO + SORT 检测与跟踪程序
- `deploy`：MySQL、EMQX、MediaMTX 及本地服务启动脚本

## 当前基线

当前源码已实现 P0 修复：后台独立监测、SQLite 持久待发、MQTT 业务确认与重试、事务幂等聚合、Session/CSRF/角色授权及短期预览授权。浏览器查询业务结果，不再负责自动告警落库或检测任务续租。

方案及验证结果见 [P0 实施方案](docs/p0-remediation-plan.md)、[P0 实现与验证记录](docs/p0-implementation-results.md)。真实现场精度、多路容量、长期稳定性与完整媒体/通知链路仍需后续验收；本轮代码验证不代表已完成生产交付。

当前机器已完成 [本机验收部署](docs/p0-local-deployment.md)，可查看页面地址、登录凭据位置和循环样例的验证步骤。

最新结论见 [P0 完整复验与补修报告](docs/p0-revalidation-2026-11-10.md)：本轮补修了旧回归漏测的并发、时间和冷启动问题，并记录实际升级中断与恢复。

进入 P1 前的 [前端核心交互检查](docs/frontend-interaction-review-2026-11-10.md) 记录了 6 类核心问题；F01–F04 已完成 [修复与验证](docs/frontend-f01-f04-results-2026-11-10.md) 并更新本机版本。

[P1 第一批实现与验证](docs/p1-alarm-implementation-results-2026-11-11.md) 完成风险规则/状态、有限续接、持久提醒与截图。[P1 后续完整复验](docs/p1-completion-results-2026-11-11.md) 又补齐独立源录像（30 天、2 TB 应用预算）、公平推理与最新帧、真实健康统计、人工处置版本冲突、通知待发/回执配置、项目守护与 F06 手工坐标降级，并已备份迁移、更新本机服务。刷新 3000 页面并重新登录可验证。真实短信未配置，现场精度/遮挡、合同容量/长期运行、OS 自启动与干净环境部署仍需独立验收；不能据代码回归声称已完成生产交付。

本仓库不包含本地虚拟环境、Node.js 依赖、构建产物、模型权重、测试视频和真实环境变量。首次部署需准备运行资源及私有 `.env`、`.env.p0`；已有部署切换前必须完成增量数据库迁移与服务身份配置，详见 [切换说明](deploy/P0-ROLLOUT.md)。

部署方式、服务端口、构建命令、当前限制和推荐代码阅读顺序参见 [部署说明](deploy/README.md)。

## 安全提示

仓库中的初始化数据仅用于本地验证。新版本默认不接受旧 MD5 口令，不开放公开注册；应在对外开放前使用离线管理员引导命令设置 BCrypt 口令。MQTT 要求独立服务凭据与 ACL，跨主机使用 TLS；后端、预览网关、媒体端口及 Broker 管理端口默认限环回访问。

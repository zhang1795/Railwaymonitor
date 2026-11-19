# P1 最终复验摘要

仅保留脱敏后的结果，不公开真实凭据、Cookie、视频地址、用户业务内容或完整日志。

- [用例数量](suite-summary.json)：H2 95、真实 MySQL/TLS MQTT 96、检测 Python 85、网关 5、部署 13、前端 55，均通过。
- [隔离运行包](isolated-runtime.json)：`runMode=FULL`，包含真实 60 秒、断库/后端强杀、实际模型、认证 RTSP、双会话预览、源码客户端重连、录像解码/Range 和三路同时窗口指标；结果绑定运行包哈希。60 秒风险使用可控合成输入，媒体和三路推理另用真实模型，不是现场精度验收。
- [隔离库恢复](isolated-restore.json)：29 表逐表行数一致。
- [业务切换](business-rollout.json)：原启用意图和历史数量保留，记录就绪/检测恢复耗时。
- [业务备份恢复](business-backup-restore.json)：真实切换前备份在隔离临时库恢复，原 84 条历史、1254 行原事件人工处置字段和风险规则一致。临时恢复库已删除，未用旧备份覆盖业务库。
- [业务 HTTP/预览](business-http.json) 与 [业务存储](business-storage.json)：只读检查和新建临时登录/预览会话，不操作真实告警已读或人工处理。
- [4K 队列对照](media-queue-comparison.json)、[60 秒整段验证](media-queue-60s.json)、[转发配置切换](media-queue-rollout.json)、[修复后三段业务录像](business-media-after-fix.json)：补验发现初次只验首帧不足，4K 默认转发队列下有码流损坏。8192 队列验证和实际修复后严格整段解码均为 0 错误；旧损坏片段原样保留。`business-storage.json` 已明确初次检查的限制，不能把首帧成功误读成整段通过。
- [继续后的运行核查](final-live-audit.json)：核心进程自本轮发布约 141.5 分钟后 PID 仍一致、近期推理正常，事件/录像待发及失败为 0，最新闭合录像整段解码通过。期间有已记录的转发参数切换，不能将 PID 一致误解为摄像头全程没有中断，也不能代替 24/72 小时验收。

前端检查执行生产组件脚本、Vue 响应式与 ECharts 实例，没有实际浏览器 DOM 点击/地图实景验证。完整私有日志在 `workspace/runtime/p1-completion/`，私有业务备份在 `workspace/runtime/p1-rollout/20261111-121514-stability/`。

测试重跑步骤见 [发布说明](../../../deploy/P1-STABILITY-ROLLOUT.md)。先准备隔离环境，再通过私有 `services.env` 向 Maven/驱动传入测试参数；测试只允许 13317/18884/18554 等隔离端口。`P1_REAL_ONLY=true` 只用于媒体调试，不能替代 `FULL` 的完整结果。

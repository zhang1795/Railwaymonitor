# P1 稳定性、录像与通知版本切换

本批在已部署的 P0、F01–F04 与第一批 P1 告警版本上增量发布。原记录保留在 [第一批报告](../docs/p1-alarm-implementation-results-2026-11-11.md)。本机后端为 18080、MySQL 为 3307，另一项目的 8080 不在操作范围内。

## 配置与边界

- `FULL_RECORDING_ROOT` 为后端与检测节点共享的持久目录；本机同用户、同文件系统。多机器部署必须挂载同一受控卷，当前协议只登记闭合文件元数据，不通过 HTTP 复制录像正文。不具备共享存储时保留 425 待发，不能宣称录像已经上传。
- `SOURCE_RECORDING_ENABLED=true`，源流由独立 FFmpeg 进程复制视频编码，默认按 30 秒切段（实际受关键帧间隔影响），检测抽帧不决定源录像帧率。音频不录制，源编码需要播放器支持。
- `LIVE_RESULTS_ENABLED=true` 共享同次推理图像与结果；`ANALYSIS_RECORDING_ENABLED=true` 额外留存目标出现前后 2 秒及持续期间的检测采样，`ANALYSIS_MAX_SAMPLE_FPS=2`。这是独立的真实推理采样回放，使用观测时间编码 VFR，与原始录像共享预算。旧 `SAMPLED_RECORDING_ENABLED=false` 保持关闭，不能用它替代新回放。详情见[输入质量与检测展示实施报告](../docs/frame-quality-and-detection-views-results-2026-11-11.md)。
- `RECORDING_RETENTION_DAYS=30`，`RECORDING_MAX_BYTES=2000000000000`（十进制 2 TB），为截图另预留默认 1 GiB。物理剩余空间低于 `RECORDING_MIN_FREE_BYTES=1073741824` 也会停止录像并重试。应用按闭合文件即时记账、活动文件大小和一分钟目录核对控制用量；硬磁盘配额应由专用卷/文件系统另设。不会为腾空间提前删除未到期录像；不删除旧的非托管文件。
- 30 天是最长保留时间，不是所有码率/路数下的容量承诺。2 TB / 30 天约支持总计 6.17 Mbit/s，尚未扣除截图和容器开销。部署应按真实总码率核算；本机还与其他数据共用磁盘。
- 录像时段使用录制节点启动时钟和媒体相对时间估计，未验证摄像机源时间。告警详情按同摄像头/同会话的重叠时段关联，不能声称逐帧对时。
- 站内通知始终启用。Webhook 需要 HTTPS 地址和至少 32 字符密钥；`X-Notification-Id` 稳定，接收方须按该 ID 幂等。签名为 HMAC-SHA256，原文 `id + "\n" + time + "\n" + sha256(body)`；接收端还需校验时间窗口并防重放。
- 短信配置使用 `.env.p0.example` 中的阿里云 AK/Secret、签名、模板、明确号码和模板变量映射。默认等级 ≥3 的首次/升级与监测故障通知；持续提醒只走站内/Webhook。未配置不生成外发任务，不补发接通前的历史通知。
- SMS 的 `ACCEPTED` 仅为受理，轮询回执后才可能为 `DELIVERED`；超时结果不明为 `UNKNOWN`，不盲目重发。管理员核查后可手动重试，可能重复收费/通知。Webhook 的 `ACKNOWLEDGED` 只表示接收服务响应成功。

短信 API 本身不幂等，验收须包含超时后的回执核查，参见 [SendSms](https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi-2017-05-25-sendsms)、[QuerySendDetails](https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi-2017-05-25-querysenddetails)。ACS3 签名实现用[官方固定向量](https://help.aliyun.com/zh/sdk/product-overview/v3-request-structure-and-signature)校验。

## 发布顺序

1. 完成 Python、前端、H2、真实 MySQL、TLS MQTT 及运行包验收；测试库严格为 13317 / `railway_p0_test`，不要对业务库运行测试初始化脚本。
2. 备份业务库、私有环境、进程参数与 SQLite WAL 一致性快照；保留当前不可变 Java/Python 包。逻辑备份恢复应在隔离库演练。
3. 执行附加且可重复的 `db/p1-alarm-migration.sql`、`db/p1-stability-migration.sql`、`db/p1-visualization-migration.sql`、`db/risk-template-migration.sql`。执行 `deploy/apply_stability_indexes.py --socket <业务socket> --database railway_monitoring`。若现存有效摄像头名称冲突，脚本拒绝建立唯一索引，保留数据，先明确处理冲突。
4. 将 Java、检测源码、预览网关分别通过 `stage_backend.py`、`stage_detector.py`、`stage_gateway.py` 固化。网关使用项目 Python 环境中的 Gunicorn，单 gthread worker / 80 线程；WebSocket 连接占用线程，需与预览上限一起评估，参见 [Flask-Sock 部署文档](https://flask-sock.readthedocs.io/en/latest/web_servers.html)。不要再用 Flask 开发服务器承载交付流量。
5. 停守护，再切后端并检查 `/api/health/ready`；切网关；最后优雅停止检测节点、备份待发并启动新节点。保持 worker 身份、输出目录、启用意图；不得同时启动两个相同 outbox 的检测进程。不修改现场风险区域和真实已读/处置数据。
6. 验证有效推理、录像登记/授权/Range 读取、原历史数量、待发收敛和错误，再启用守护并记录中断时间。当前本机可使用 `python3 deploy/rollout_stability.py --apply --acceptance-directory workspace/runtime/p0-reaudit/p3`；脚本检查完整隔离验收的运行指纹与待发布包一致，自动生成新的私有备份目录，不能通用于其他部署。保留视频发布源的已有守护配置；摄像头原已停用时不得将“无需恢复”写成已完成业务有效推理验证。

## 单独发布告警策略设置

已完成 P1 可视化迁移的环境，在备份业务库后执行 [risk-template-migration.sql](../web-springboot/src/main/resources/db/risk-template-migration.sql)，发布新版 Java 后端和配套前端。迁移为已有摄像头保留原规则，导入两个场景模板，全局默认初始为空。管理员在“告警策略设置”页配置单路摄像头、选择全局默认和维护场景模板。“摄像头管理 → 风险规则”也可以打开单路编辑器。

上线后以普通账号在“实时监控”选择机位，核对规则摘要。需要调整机位时，管理员在参考画面上校准区域、停用该路检测、保存规则，再启用检测。发布模板新版后，在升级预览中核对每路的实际参数变化并勾选目标机位。升级前的异常事件详情仍显示事件发生时保存的规则。

## 守护与运维

`start.sh` 保存 600 权限的 `workspace/runtime/managed-services.json` 并启动项目守护。守护校验 PID、命令和工作目录，单实例文件锁，5–60 秒退避；仅恢复本项目后端、网关和检测进程。数据库/Broker 暂不可用通过 readiness 与持久监测故障报告，不因为依赖故障无限重启健康应用进程。

检测主循环每 2 秒报告不含视频地址的心跳。启动容忍 180 秒后，进程心跳过期或任务超过 `DETECTOR_STALL_SECONDS=120` 无有效推理，连续三次检查失败后先 TERM，再按原生卡死的上限处理。重建检测进程会建立新会话，物理目标身份不能跨会话自动续接。阈值必须结合约定路数和硬件校准。

`stop.sh` 先停守护，再停检测/预览/后端；身份不匹配或退出超时保留 PID 并停止后续关库，不假报成功。`status.sh` 检查 readiness、守护报告与 MySQL。

本机另将受控目录内的两路样例发布进程纳入守护；只接受本项目 FFmpeg、已知本地视频和本机 8554 目的地址，拒绝其他项目文件或远端发布目标。生产外部摄像机本身不由此守护管理。

`MEDIA_WRITE_QUEUE_SIZE=8192` 是本次 4K 样例对照验证后的 MediaMTX 写队列配置。默认 512 时实际录像含损坏关键帧；8192 通过 60 秒循环和三段业务录像整段严格解码。当前镜像仍为 1.18.2，不能把镜像版本切换当成本次修复。队列增加会消耗更多内存，需结合读者数量、码率评估。录像验收必须解码整段并检查错误输出，首帧成功或 SHA 匹配均不能代替码流完整性检查。

[systemd 模板](systemd/railway-guardian.service.example)和[日志轮转模板](systemd/railway-logrotate.conf.example)需替换实际用户/路径后交主机运维安装；当前不会擅自修改主机服务。未安装 OS 守护时，不能承诺主机重启后自动恢复或守护进程自身被强杀后自动拉起。本机 Vite 是开发入口；对外部署仍应使用构建 dist、TLS 反向代理及受控内部服务入口。

后端 `/api/health/live` 只表示进程可响应；`ready` 校验数据库和 MQTT 订阅，不代表每个摄像头已有效推理。监测页与持久故障收件箱使用实际帧/推理采样。历史未采样保持未知，不重建虚假设备在线率。

失败时保留新数据和待发，优先切回已保存的旧不可变运行包；附加迁移不删表回滚，不用旧整库覆盖发布期间新增数据。真实渠道、现场模型精度、压力上限与长时运行必须单独验收。

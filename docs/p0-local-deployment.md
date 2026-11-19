# P0 本机验收部署记录

日期：2026-11-10（Asia/Shanghai）。用户要求重新构建并打开验证后，已完成本机版本切换。此记录补充此前仅做隔离验证的 [实现记录](p0-implementation-results.md)。

## 访问与登录

- 页面：**http://127.0.0.1:3000/**。
- 账号：`p0_admin`。随机口令保存在私有文件 [login-credentials.json](../workspace/runtime/p0-rollout/login-credentials.json)，权限为 600，文件不提交 Git。
- 若通过 VS Code Remote SSH 使用服务器，在“端口”面板转发服务器 3000 到本机 **3000**，然后打开上面的地址。API 和视频 WebSocket 都经过页面同源代理，不必额外转发其它端口。
- 浏览器自动控制连接本次不可用；已通过实际 HTTP 会话和 WebSocket 客户端验证登录、预览与检测入库，未将其描述为可视化页面验收。

本次是**环回 HTTP/MQTT 本机验收模式**，私有配置显式允许本地明文，Session Secure Cookie 仅在此模式关闭。对外部署仍需按 [切换指南](../deploy/P0-ROLLOUT.md) 使用 HTTPS/TLS 和相应配置，不能直接将开发端口开放公网。

## 实际运行结构

| 服务 | 当前地址 | 运行方式 |
| --- | --- | --- |
| Vue/Vite | `127.0.0.1:3000` | 宿主机独立进程 |
| Spring Boot | `127.0.0.1:18080/api` | 宿主机最终 jar |
| Flask | `127.0.0.1:5000` | 宿主机独立进程 |
| MySQL | `127.0.0.1:3307` | 原有项目数据目录 |
| EMQX | `127.0.0.1:1883` / 管理 `18083` | 重建的 `railway-emqx`，保留数据卷 |
| MediaMTX | `127.0.0.1:8554` | 重建的 `railway-mediamtx` |
| 检测节点 | `detector-1` | 宿主机 Python，SQLite 持久待发 |
| 样例发布 | `rtsp://127.0.0.1:8554/p0_demo` | 循环本地视频，无现场数据 |

8080 已由另一个项目使用，因此本项目后端使用 18080；`SERVER_PORT`、`BACKEND_INTERNAL_URL`、`VITE_API_PROXY_TARGET` 已保持一致。其它项目未停止。

旧 Docker 网段 `172.18.0.0/16` 与本机 sing-box 的 `/30` 路由重叠，导致旧网段中的容器连接被重置。本次只将本项目切换到 `railway-monitoring-p0` 独立网络（本轮分配 `172.21.0.0/16`），没有修改全局路由或代理。Compose 更换网络后使用 `--force-recreate` 更新容器网络引用。

宿主机进程启动方式已改为独立会话，防止随启动终端退出。前端直接运行 Vite 的 Node 入口，PID 对应实际服务进程。

后续 [P0 完整复验](p0-revalidation-2026-11-10.md) 补充了按哈希保存运行包：后端从 `workspace/runtime/releases/backend/<SHA256>/` 启动，不再直接运行 Maven 构建目录。本轮补修升级曾引起一次监测中断，已恢复；详情以复验报告为准。

## 数据备份与迁移

备份目录：`workspace/runtime/p0-rollout/20261110-143006/`。当前目录指针为 `workspace/runtime/p0-rollout/current`。备份为本机私有文件，不提交 Git。

已保存 MySQL 停机冷备、逻辑导出、原部署配置、容器元数据、停机 Broker 数据，以及验收后的 outbox 一致性备份。逻辑导出曾恢复到随机命名的临时库，核对行数后删除该临时库。

已对原 `railway_monitoring` 执行一次 `p0-migration.sql`：迁移前后均为 **2 个用户、13 台摄像头、84 条异常记录**。之后新增一个独立验收管理员和一个样例摄像头；验收产生的告警具有独立来源键，原有 84 条历史异常仍保留。

没有执行仓库旧的全量初始化 SQL，没有清空业务库或 Broker 数据卷。Dashboard 与两个 MQTT 服务身份已使用随机凭据，浏览器不连接 MQTT。

## 直接验证

1. 使用验收账号登录，进入“实时监控”。
2. 选择 **P0本地验收样例（循环视频）**（摄像头 ID **21**），可观看本地循环视频。
3. 管理员点击“启用后台检测”，在“异常事件”中按该摄像头查询结果。
4. 关闭预览或页面后，后台监测仍由持久配置管理；验证结束应显式“停用后台检测”。

本轮已经使用真实 YOLO 权重和 CPU 推理，在没有页面写入参与的情况下创建了“牛”告警 **293**；HTTP Session/CSRF、同源 API、授权 JPEG 预览通过。验收后该任务为 STOPPED、enabled=false，SQLite 待发为 0。样例流与服务保留运行，供用户继续操作。这只是功能验收，不是现场精度或多路性能指标。

机器可读结果：[local-deployment.json](test-results/p0/local-deployment.json)。

## 启停

在已启用 Node 22 的终端、项目根目录执行：

```bash
./deploy/status.sh
./deploy/start.sh --with-detector --with-demo
./deploy/stop.sh
```

`--with-demo` 使用本机已有 `workspace/runtime/smoke-cow-short.mp4`，可用 `P0_DEMO_VIDEO` 指定其它可信样例；它不自动创建或启用摄像头任务。停止脚本包含样例发布进程，保留数据库和 Docker 数据卷。日志及 PID 位于 `workspace/runtime/logs`、`workspace/runtime/pids`。

2026-11-10 后续已更新 [前端 F01–F04 修复版本](frontend-f01-f04-results-2026-11-10.md)：离线设备可停用检测，状态与画面过期可见，全局未读告警可查看。刷新 3000 页面并重新登录即可验证。首次提醒包含没有已读回执的历史告警；已读与已处理分别记录。检测进程及原监测会话在本次切换中保留。

2026-11-11 已进一步切换 [P1 告警第一批版本](p1-alarm-implementation-results-2026-11-11.md)：新增规则、风险状态、持续提醒与截图。本次检测进程实际重启并建立新会话，恢复至 RUNNING 约 7.9 秒，摄像头 21 保持停用、22 保持启用，84 条原始记录保留。当前仍访问 3000，刷新并重新登录；未配置规则继续显示待核验观察，现场区域和阈值需另行校准。

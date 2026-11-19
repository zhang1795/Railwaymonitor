# F01–F04 修复验证证据

对应 [修复报告](../../frontend-f01-f04-results-2026-11-10.md)。此前 [审查复现目录](../frontend-interaction-audit-2026-11-10/README.md) 是历史缺陷快照，其确认旧缺陷存在的断言不属于当前修复验收。

- `monitor.txt`：当前页面脚本 6 项。
- `preview.txt`：生产 WebSocket 客户端及播放器 11 项。
- `inbox.txt`：提醒与异常页 8 项。
- `backend-h2.txt`：55 项完整回归摘要。
- `backend-h2-notices-final.txt`：最终 5 项通知相关回归。
- `backend-mysql-mqtt.txt`：55 项真实 MySQL 与 1 项 TLS MQTT 故障集成摘要。
- `runtime.json`：真实运行组合及当前生产预览客户端连线结果。
- `frontend-build.txt`：最终 Vite 构建，vue-tsc 在其前成功执行。
- `deployment.json`：更新后的健康、任务配置、会话保留及实际待发；本次检查没有标记真实告警已读。

私有日志在 `workspace/runtime/p0-reaudit/f1/`，业务备份在 `workspace/runtime/frontend-rollout/20261110-f01-f04/`；不提交凭据、令牌和业务导出。

仓库根目录，准备 Node 22 与现有依赖后运行：

```bash
node web-vue/tests/monitor-lifecycle.test.cjs
node web-vue/tests/secure-preview.test.cjs
node web-vue/tests/alarm-inbox.test.cjs
```

夹具执行生产脚本并使用真正的 Vue 响应式状态，替换网络、时钟和画布；不是 DOM 测试。真实连线由 `p0-live-acceptance.cjs` 另行执行，包含当前生产客户端。

后端和运行组合沿用 [隔离环境流程](../p0-reaudit-2026-11-10/README.md)。使用短目录，如 `workspace/runtime/p0-reaudit/f2`，避免 Unix socket 超长；初始化器已增加长度预检。只允许 13317 的 `railway_p0_test`，不得换成业务库。测试 schema 会一并执行通知迁移。本轮测试服务已清理。

浏览器宿主不可用，未声明完成视觉或实际点击验收。

# 前端核心交互检查证据

对应 [检查报告](../../frontend-interaction-review-2026-11-10.md)，日期 2026-11-10（Asia/Shanghai）。未做真实浏览器 DOM 点击和地图可视化验收。

> F01–F04 后续已修复。此目录保留修复前证据，`reproduce.cjs` 的旧缺陷断言不用于当前代码验收；当前回归及复跑入口见 [修复验证目录](../frontend-fixes-2026-11-10/README.md)。

- `reproduce.cjs`：执行当前生产 SFC 脚本和 WebSocket 客户端，使用内存接口、可推进时钟、画布替身及真正的 Vue 响应式效果。7 项断言用于**复现现有问题**，通过不表示修复通过。F05 为模板与真实接口核对，没有用重复模板实现的测试充当渲染验收。
- `reproductions.txt`：7 项复现输出。
- `current-monitor-baseline.txt`：既有当前监控组件 4 项测试输出。
- `secure-preview-baseline.txt`：既有授权预览客户端 2 项测试输出。
- `read_only_api.py`：仅访问本机 `127.0.0.1:18080` 验收 API；POST 只用于本次登录、CSRF 与退出。凭据读取私有本机文件，不输出密码、令牌、用户联系方式或摄像头源地址。
- `read-only-api.json`：脱敏只读快照，包含设备状态、任务状态、最新事件部分检测字段及统计接口响应形状；业务写入为 0。

从仓库根目录执行（需已准备项目 Node 依赖）：

```bash
node docs/test-results/frontend-interaction-audit-2026-11-10/reproduce.cjs
node web-vue/tests/monitor-lifecycle.test.cjs
node web-vue/tests/secure-preview.test.cjs
```

本轮直接执行 Node 脚本，输出逐条用例及计数；本机 Node 路径为 `/home/a6411/.nvm/versions/node/v22.19.0/bin/node`。

此外实际执行了 `vue-tsc -b` 和 `vite build`，两者退出码均为 0，Vite 构建了 2200 个模块。构建通过只说明类型/编译门槛，不验证交互正确。地图配置检查仅记录两项配置存在，未输出其值，也未外联核验密钥有效性。

现有业务摄像头、告警、监测启用配置均未修改；本轮登录会话已经退出，未重启服务。

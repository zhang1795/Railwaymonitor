# P0 版本切换与回退

本文是通用切换操作说明。实现阶段曾保留旧部署，后续用户要求运行验证，已完成一次 [本机验收切换](../docs/p0-local-deployment.md)；其它环境应独立安排迁移和切换。业务库迁移、既有 Broker 凭据调整与进程切换应安排在维护窗口；当前工作区还包含之前的未提交修改，打包时应保留其完整快照。

## 1. 新版本运行契约

前端 F01–F04 版本新增按账号保存的告警已读回执。已有 P0 数据库备份后只执行 `web-springboot/src/main/resources/db/frontend-notices-migration.sql`，再更新后端包与前端资源；不要重跑已完成的 P0 ALTER 迁移。首次安装则在 P0 迁移后执行此文件。详见 [本轮结果](../docs/frontend-f01-f04-results-2026-11-10.md)。

- Vue → 同源 HTTPS `/api`、`/stream/ws`；不再直接连接 MQTT。
- Spring Boot → MySQL；使用 `railway-backend` 独立 MQTT 账号，消费事件并在事务提交后确认。
- 检测进程 → SQLite 本地持久目录及 `detector-1` MQTT 身份。每个身份只能运行一个实例，不共用 SQLite 文件。
- Flask → 内部后端，使用 `PREVIEW_SERVICE_KEY` 消费短期预览授权。浏览器不传流地址；源地址来自服务器摄像头配置。
- 自动检测由 `/monitoring` 的持久启用配置决定。关闭预览、刷新或退出页面不停止检测。管理员需要显式启用/停用。
- 自动告警初始为 1 级待核验观察，置信度只表示该类别识别证据；人工处置与检测结束是两个维度。

## 2. 迁移前

1. 备份当前源码/配置与数据库一致性导出，记录版本和模型哈希；不要输出 `.env` 内容到日志。
2. 校验备份可恢复到隔离库。旧版本尚无持久待发库，不能承诺切换期间的旧内存结果零损失；应记录维护盲区并用已保存视频核验。
3. 从 `.env.p0.example` 创建 **未提交的** `.env.p0`，为三个服务身份、节点 Cookie、预览服务密钥分别生成随机值。生成命令可使用 `openssl rand -hex 24`，不要复用账号或使用示例占位符。
4. 准备 HTTPS 与 MQTT TLS 的真实证书/私钥，SAN 匹配连接的主机名，配置 `MQTT_CA_FILE`、`MQTT_SERVER_CERT`、`MQTT_SERVER_KEY`。私钥只允许宿主机管理员和容器运行身份读取。
5. 配置允许的摄像头主机 `CAMERA_ALLOWED_HOSTS` 与精确的页面 Origin `PREVIEW_ALLOWED_ORIGINS`。默认只允许环回摄像头地址。

EMQX 固定使用现有 5.8.8 镜像，服务账号不是 Dashboard 管理员。`prepare_p0_broker.py` 生成无凭据的 ACL/config 文件，节点 Cookie 由 `EMQX_NODE__COOKIE` 提供。账号由环回管理 API 初始化，匿名不放行。已有 EMQX 数据卷的 Dashboard 口令不会因修改 DEFAULT_PASSWORD 自动重置，需使用实际有效管理员凭据完成迁移并单独轮换；脚本失败时应处理凭据，不清空业务数据卷。

## 3. 数据库增量迁移

迁移文件：[p0-migration.sql](../web-springboot/src/main/resources/db/p0-migration.sql)。它不删除旧库、旧表或历史告警，只增加列、表和索引。使用数据库客户端连接已确认的目标库，**执行一次**。MySQL DDL 不是整文件事务；遇错立即停止，核对已经完成的语句，不要盲目重复整文件。

新增自动告警以 source_key 唯一；历史事件 source_key 为空，不伪造检测身份。人工字段保留。新 first_seen/last_seen 为 UTC；现有 event_time 保持上海当地时间的接口兼容语义。

启动有只读 schema 检查，迁移未完成会明确失败。迁移在 H2 和独立 MySQL 5.7.24 上测试；它不依赖 MySQL 8 的 CHECK 约束来保证核心行为。生产数据库版本与升级维护策略仍应单独确认。

## 4. 账号引导和安全默认值

默认禁止旧 MD5 登录、禁止公开注册、禁止固定口令重置，Session Cookie 默认 Secure/HttpOnly/SameSite=Strict。不要把种子账号 `admin/123456` 暴露到公网后再修改。

构建后可以使用显式的离线管理命令，在 HTTPS 对外开放之前为管理员设置新 BCrypt 口令。该命令要求显式 DB_URL/DB_USERNAME/DB_PASSWORD，密码从交互终端或标准输入读取，不通过参数或日志传递：

```bash
java -Dloader.main=com.example.security.AdminBootstrap \
  -cp web-springboot/target/railway-monitoring-1.0.0.jar \
  org.springframework.boot.loader.launch.PropertiesLauncher
```

此命令具有创建/恢复管理员的权限，应仅由持有数据库凭据的部署人员使用，不能作为公网 API。可使用 P0_ADMIN_USERNAME 指定账户。初始化会使该账户旧会话失效。

`ALLOW_LEGACY_MD5_LOGIN=true` 仅用于受控迁移：旧口令验证后立即升级哈希并要求修改口令；修改前不能使用业务 API。完成迁移后关闭该开关。管理员重置生成一次性显示的随机临时口令，用户必须修改；不自动向任何人发送消息。

## 5. 构建与受控切换

先通过本轮验证命令，再构建 jar 和前端 dist。停止旧检测程序与旧前端的告警写入路径，防止旧页面继续使用过时协议。新旧协议分开使用 v3 Topic，生产 ACL 不允许旧页面发布控制或告警。

长驻后端不得直接运行 Maven `target/` 中会被下一次构建覆盖的 jar。`start.sh` 通过 `stage_backend.py` 按 SHA256 发布独立只读副本，再从 `workspace/runtime/releases/backend/<SHA256>/` 启动。升级时构建完成后停止旧后端再启动新版本，不能用原地覆盖运行包完成热更新。运行中的旧版本目录应保留到其进程完全退出；不要为了清理磁盘删除正在运行的包。

`deploy/start.sh --with-detector` 现在要求 `.env.p0`，自动选择 TLS Compose 覆盖配置、初始化指定 Broker 服务账号，再启动进程。Nginx 使用 [nginx-p0.conf](nginx-p0.conf) 的同源路径；对外屏蔽 `/api/_internal/`，后端/Flask 端口仅开放可信内网/环回。不要在公网暴露 Vite 开发服务器或 EMQX 管理端口。

脚本仍是本机联调用途，完整 systemd/容器守护、备份计划与生产容量属于后续运维项。明文 MQTT 仅在显式 `MQTT_ALLOW_LOCAL_PLAINTEXT=true` 且客户端连接环回地址时允许；远程工作节点必须启用 TLS。跨主机部署时，需显式调整 TLS 监听的发布地址和防火墙，不开放 1883/8083。

仅在隔离本地开发、使用 HTTP 时，可以明确设置 SESSION_COOKIE_SECURE=false；正式 HTTPS 环境保持 true。

## 6. 切换验收

- 登录管理员，确认用户响应没有密码/哈希，普通用户不能管理账号、摄像头或后台监测。
- 管理员启用一台授权摄像头，确认 STARTING → RUNNING；关闭所有浏览器，仍产生后端事件。
- 再打开页面查看已有告警；多页面不会重复创建；停用监测后旧控制不能重新启动。
- 同一轨迹类别纠正和置信度对应，自动更新不覆盖已人工处理状态。
- 临时断开链路或重启测试 Broker：待发数增长但内存有界；恢复后待发清空且自动告警不重复。
- 确认匿名、错误口令、跨 worker Topic、伪造 ACK/控制、错误 TLS 证书被拒绝。
- 检测异常、控制租约过期与磁盘满明确报告；不能只检查进程是否存在。

## 7. 回退

回退前停止新控制和接收入口，保留新 SQLite **及 WAL**、接收记录、监测配置和数据库备份。SQLite 使用备份 API 或在进程完全停止后备份，不能运行时只复制 `.db`。

停用 monitoring_task 的 enabled 后，确认新检测工作节点停止；不要仅关闭页面。回退应用可保留新增表/列，但旧版存在原报告中的 P0 缺陷，不能在开放公网的情况下恢复匿名 Broker 或无认证写接口。恢复旧界面不代表恢复交付质量。

新版本没有自动删除待发记录的过期策略，容量达到上限会明确停止接收新关键事件。有效接收/拒绝数据的长期归档与保留策略仍需作为数据生命周期工作制定；不要直接清空持久表来消除积压。

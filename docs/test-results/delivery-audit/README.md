# 2026-11-10 交付审查证据

主报告：[delivery-readiness-review-2026-11-10.md](../../delivery-readiness-review-2026-11-10.md)。

这些脚本针对修复前业务模块或页面聚合函数。P0 改动后，原缺陷探针可能失败或无法提取已删除的函数，应查看 [P0 回归证据](../p0/README.md)。它们记录缺陷，断言仅用于保证复现场景确实触发，**不应将这些断言当成未来正确实现的验收标准**。

没有连接网络服务、业务数据库或真实摄像头。Python worker 使用假帧/检测/写入器，前端使用假 HTTP/定时器，预览脚本构造源代码可以产生的跨用户任务状态。由此证明的是代码行为，不是现场故障频率、模型精度或硬件吞吐。

## 隔离复跑

在项目根目录执行，Node 需能访问前端已有 TypeScript 依赖：

```bash
PYTHONDONTWRITEBYTECODE=1 workspace/runtime/detector-env/bin/python docs/test-results/delivery-audit/reproduce_detector.py
node docs/test-results/delivery-audit/reproduce_frontend.cjs
PYTHONDONTWRITEBYTECODE=1 workspace/runtime/flask-venv/bin/python docs/test-results/delivery-audit/reproduce_preview.py
PYTHONDONTWRITEBYTECODE=1 workspace/runtime/detector-env/bin/python docs/test-results/delivery-audit/inspect_weights.py
```

本机 Node 使用 `/home/a6411/.nvm/versions/node/v22.19.0/bin/node`。结果分别保存于 [detector.json](detector.json)、[frontend.json](frontend.json)、[preview.json](preview.json)。探针传入的演示日期不代表用户实际事件。

`inspect_weights.py` 是独立的模型结构只读检查，会加载本地已有可信权重，结果为 [model-inspection.json](model-inspection.json)，不属于无权重的隔离探针。

## 本次既有验证执行摘要

- `PYTHONDONTWRITEBYTECODE=1 workspace/runtime/detector-env/bin/python -m unittest discover -s RailwayDetector/tests -v`：49 项通过，报告 `Ran 49 tests in 11.517s`。
- `node web-vue/tests/detector-tasks.test.cjs`：11 项通过、0 失败。
- `npm run build`：vue-tsc 类型检查及 Vite 构建成功，Vite 6.3.6，2199 modules transformed。构建耗时不作为产品性能指标。
- 后端使用仓库本地 Maven 缓存与 JDK17，执行离线 `mvn test`：BUILD SUCCESS，明确输出 `No tests to run`。没有启动 Spring 应用或访问数据库。
- `PYTHONDONTWRITEBYTECODE=1 workspace/runtime/detector-env/bin/python RailwayDetector/tests/smoke_real_model.py`：3 帧及 4 种尺寸对比通过，输出从 `workspace/runtime/bugfix-tests/real-model-smoke.json` 复制至 [real-model-smoke.json](real-model-smoke.json)。该测试会加载已有可信模型权重，但不访问业务服务。

后端命令在 `web-springboot` 目录执行：

```bash
env JAVA_HOME=../workspace/runtime/jdk17/usr/lib/jvm/java-17-openjdk-amd64 \
  ../../apache-maven-3.9.9/bin/mvn -o \
  -gs ../deploy/maven-settings.xml -s ../deploy/maven-settings.xml \
  -Dmaven.repo.local=../workspace/runtime/m2 test
```

上述既有验证的本次原始输出见审查会话工具记录；此处记录执行摘要，没有将历史日志伪作本次原始日志。之前批次的原始记录仍保留在 `../batches-ab/`。

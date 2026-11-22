# VeriFlow v0.3.2 — 本地验证记录

> 此文为v0.3.2历史记录。最新v0.3.3-rc.1结果见 [云端验收记录](CLOUD_UAT_2026-11-22.md)。

日期：2026-11-22（Asia/Kuala_Lumpur）

## 已实际执行

| 检查项 | 方法 | 结果 |
| --- | --- | --- |
| 原有后端逻辑/授权测试 | `pytest -q` | **20/20 PASS**（本轮） |
| 前端JavaScript语法 | `node --check app/static/app.js` | **PASS** |
| Docker Compose配置 | Python PyYAML解析`compose.yml`和`compose.postgres.yml` | **解析通过**；本运行环境无Docker引擎，不能据此称镜像构建成功 |
| 本机HTTP存活检查 | uvicorn启动，访问`/api/health` | **HTTP 200** |
| 数据持久化检查 | 另一独立uvicorn进程读取同一个SQLite文件 | **PASS**：保留4工单、8项已验收UAT及独立审批记录 |
| 匿名API限制 | 未登录访问`/api/projects` | **401** |
| 真实HTTP多用户业务集成验收 | `scripts/live_api_uat.py` | **15/15 PASS**（详见随附测试摘要） |
| Chromium真实网页导航 | Playwright启动系统Chromium打开本机站点 | **环境阻断**：`net::ERR_BLOCKED_BY_ADMINISTRATOR`，无法判定应用UI通过或失败 |
| Docker镜像构建运行 | `docker compose up --build` | **未执行**：测试环境没有Docker二进制/Engine |
| Playwright完整UI自动流程 | `scripts/browser_uat.py` | **代码已编写，待Windows或GitHub Actions实际运行** |
| 人工业务UAT | `docs/UAT.md` 29项 | **待用户亲自执行** |
| GitHub远端仓库推送与CI | GitHub | **未执行**：`njjjna/veriflow-quality-platform` 尚不存在；不能推送到无关仓库 |

**结论：** 后端、角色权限和真实HTTP多用户流程已得到有效验证。**真实浏览器UAT、Docker跨环境复现和GitHub CI尚待验收**；当前只能称为「本地可复现工程候选版本」，不能称作已通过生产验收。

## 本轮修复/补充

- 为用户管理页增加「创建账号后直接出现在角色选择下拉框」交互，免除手动刷新造成的困扰。
- 增加PowerShell启动/停止脚本、中文本地UAT操作文档。
- 增加可重复运行的HTTP多角色集成验收脚本，覆盖管理员创建用户、强制改密码、权限隔离、工单整改与独立复测、文件上传、数据检查、重复去重、8项UAT独立验收、上线门禁、审批和CSV。
- 增加Playwright浏览器交互验收脚本，并将其接入GitHub Actions浏览器任务定义。**脚本编写完成不等于已运行通过。**

## 说明

- 此次HTTP测试使用独立临时SQLite数据库和完全虚构的账号、机构及工单数据。
- 本次测试没有访问真实患者数据、没有修改公网网站，也没有向GitHub推送。
- `VERIFLOW_MODE=production`仅为严格角色模式，不能当作安全加固已通过的证明。

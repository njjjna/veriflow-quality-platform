# VeriFlow · Enterprise-style quality & UAT workflow MVP (v0.3.3-rc.1)

> **定位**：可本地复现的企业质量管理作品集；**不是经审计的生产安全系统**。这是独立实现版本，不会自动覆盖之前的 ChatGPT Sites 私人演示网站。
>
> 所有示例机构和数据均为虚构。**严禁上传患者信息、客户保密资料或实际生产数据。**


## 0. 当前候选版本与云端验收

本轮状态见 [`docs/CLOUD_UAT_2026-11-22.md`](docs/CLOUD_UAT_2026-11-22.md)。已修复审批表单提交、隔离API/浏览器测试数据库，并补齐测试依赖。**后端20项、HTTP流程15项、前端提交处理2项已通过；当前Work云浏览器仍被访问策略阻断，浏览器UAT与GitHub发布尚未完成。**

无需Docker的独立云运行器复现方式（仅模拟数据）：

```bash
pip install -r requirements.txt -r requirements-test.txt -r requirements-browser.txt
python -m playwright install --with-deps chromium
pytest -q
node --test tests/frontend_release.test.cjs
python scripts/run_isolated_uat.py --suite all
```

每个API/浏览器套件使用全新临时SQLite、随机管理员密码和独立附件目录，运行结束自动停止服务。结果与截图在 `test-artifacts/isolated/<run-id>/`；以本次 `run_summary.json` 和 `browser/browser_result.json` 为准。仅需后端时用 `--suite api`，它会明确记录 `browser: not_run`。浏览器脚本包含五种业务角色、工单整改与复测、证据预览、CSV、8项UAT、上线门禁和双人审批；**脚本已扩展、尚未实际运行通过**。GitHub推送后将自动执行 `.github/workflows/browser.yml`。

### Windows个人电脑可选路径（无需公网）

**Windows：** 先安装并启动 Docker Desktop，确保本机可运行 `docker compose version`。解压工程包后，在工程根目录打开 PowerShell：

```powershell
./scripts/start_local.ps1 -AdminEmail 'admin@demo.invalid'
```

首次启动默认采用**本地PostgreSQL**；脚本会为它生成随机数据库密码并写入不会被Git提交的`.env`。如需简化成SQLite，可给启动与停止脚本均加 `-UseSQLite`。第一次运行会在终端提示输入两次管理员密码（至少12位）；**不会生成公开默认密码**。浏览器随后访问 `http://localhost:8000`。重复启动且已存在管理员时可加 `-NoBootstrap`。

停止服务并保留本地数据：

```powershell
./scripts/stop_local.ps1
```

**注意：** `docker compose down -v` 会删除本地数据库卷，不要随意执行。所有测试只使用虚构数据。

若暂时没有Docker，也可以使用下文 Python 本地运行方式。**本次开发环境没有Docker引擎，Compose已完成配置静态检查，但还需要你在Windows Docker Desktop上实际验证镜像构建和启动。**

**自动浏览器测试：** 启动本机服务并准备一次性管理员账号，在PowerShell中设置 `VERIFLOW_UI_URL`、`VERIFLOW_UI_EMAIL`、`VERIFLOW_UI_PASSWORD`，运行 `python scripts/browser_uat.py`。该脚本会向测试数据库增加模拟用户/工单，不允许在真实业务库运行。浏览器首次安装执行 `python -m playwright install chromium`。完整步骤见 `docs/LOCAL_UAT_GUIDE.md`。

**测试结果区分：** 当前已完成20项pytest、15项本机HTTP多角色集成验证和2项前端审批处理回归；本执行环境的Chromium因浏览器网络访问策略返回`ERR_BLOCKED_BY_ADMINISTRATOR`，故真正的浏览器自动化UAT和人工UAT仍待在本地Windows或GitHub Actions中执行，不应标注为已通过。详见 `docs/LOCAL_TEST_REPORT.md`。

---

## 1. 为什么建设？

模拟“多家医院的预约与设备接入平台上线”场景：测试/项目/整改/业务验收分别由不同角色执行，避免需求、缺陷、数据异常、验收记录长期散落在聊天和表格中。目标为 **质量规则 → 工单 → 整改 → 复测 → UAT → 上线准备摘要** 的可追溯流程。

与个人作品展示相关的核心材料在 `docs/`：业务需求、RACI与权限矩阵、指标字典、流程与数据模型、UAT用例、上线前差距清单。

## 2. 已实现范围（可以运行和验证）

| 模块 | 实现 |
| --- | --- |
| 登录 | 管理员初始化；用户创建（生成一次性临时密码）；首次强制改密；登出；12小时服务器会话 |
| 权限 | 系统管理员 + 五种项目角色；`demo` 同项目可兼任，`production` 同项目单一职责；后端项目级授权 |
| 工单 | 新增、分配、待处理→整改中→待复测→关闭或退回；整改记录和复测记录；操作审计 |
| 数据质量 | 6列模拟CSV；完整性、唯一性、状态合法性、数值范围、日期校验；检查批次；导入异常为工单；重复创建提示 |
| UAT | 8项检查；测试人员执行并填写证据；验收负责人独立审核；上传PNG/JPG/PDF附件和授权下载/图片预览 |
| 总览与上线审批 | 高风险问题、验收进度、最新质量检查；经理确认交付门禁并提交，验收负责人独立审核 |
| 导出 | 登录并授权后下载UTF-8-BOM CSV；浏览器支持时使用另存为弹窗；失败则回退普通下载 |
| 工程 | FastAPI + SQLAlchemy + SQLite（本地）/ PostgreSQL（可选，尚未完成实际部署验证）；pytest自动化测试；Docker；GitHub Actions CI 示例 |

**已知差距**：没有MFA/SSO、邮件邀请服务、数据库迁移、强制登录失败限流、备份恢复演练、生产监控、负载测试、渗透测试、审计日志防篡改、恶意软件扫描或真正企业级证据对象存储。详见 `docs/production_gap.md`。

## 3. Windows/macOS/Linux 本地运行（Python 3.11+）

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.bootstrap --email admin@example.com
# 命令行交互设置至少12位管理员密码
uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000`。初次管理员会自动拥有一个虚构医院系统项目和8项UAT检查内容。

**账号创建**：用管理员登录 → 用户与权限 → 创建用户 → 安全传递屏幕上只显示一次的临时密码 → 为该用户分配项目角色 → 用户首次登录自行修改密码。管理员不能为其他用户查看原密码。若要在多台设备协作，必须部署共享数据库与统一HTTPS站点。

**复现质量分析**：数据质量 → 载入12行模拟样本 → 执行质量检查 → 应返回 **12条记录、3条异常、记录通过率75%** → 转成工单 → 再次转换应跳过已存在的同源异常工单。

**演示上线门禁**：数据质量另有 `data/sample_institutions_clean.csv`（12条、0异常）。在前端“数据质量”可切换加载异常样本或合格样本；后者用于验证上线审批门禁，而不是篡改原测试样本结果。

**验证完整业务流程**：以管理员创建四个用户，分别赋予“项目经理、测试人员、整改负责人、验收负责人”角色；经理分配工单 → 整改负责人处理并填写措施 → 测试人员复测后关闭 → 测试人员执行UAT并填写证据 → 验收负责人审核通过。每个动作在审计日志有对应记录。可用不同浏览器/无痕窗口登录不同账号。

### v0.3 两种角色策略模式（不是公网部署状态）

- `VERIFLOW_MODE=demo`：本地演示，管理员可设置 `manager,tester` 等项目组合角色，测试更便利；**同一个人仍不能审核自己执行的UAT，也不能审核自己的上线申请**。
- `VERIFLOW_MODE=production`：**默认值**，一个人同一个项目只允许一个业务角色；平台管理员不允许执行写入业务动作。注意：这个英文配置名仅指严格职责策略，并不意味着系统经过真实生产级安全审核。
- 两套模式建议用**分离数据库和附件目录**；如果已有演示多角色数据，严格模式会拒绝直接启动，须执行数据治理，不允许直接切开关绕过控制。
- 本地Docker compose明确使用`demo`，便于演示；直接执行Python时默认严格模式。使用环境变量改变模式，例如：`VERIFLOW_MODE=demo uvicorn app.main:app --reload`（PowerShell 使用 `$env:VERIFLOW_MODE="demo"`）。

### 证据附件操作

进入「问题工单」或「UAT验收」，选择PNG/JPG/PDF文件，文件大小不能超过5MB。后端校验项目访问权限与文件头，使用随机文件名保存至`VERIFLOW_UPLOAD_DIR`指定目录，项目成员可受控下载，PNG/JPG可受控图片预览，PDF只提供下载。已审核完成的UAT、已关闭工单不能直接追加证据。

**公开部署前必须补**：病毒扫描、文件内容深入验证、配额、保留与清理、存储备份和回滚；上传前严禁使用真实医院或患者文件。

### 上线流程演示

「上线审批」按三组条件评估：①没有未关闭的高/紧急工单；②8项UAT均由不同验收负责人审核通过；③最新一次数据质量检查0异常。经理还需确认安全复核、回滚验证、备份恢复、交付文档、运维交接并填证据引用；低/中级未关闭工单需补充风险接受说明。验收负责人可独立审核，服务端复核规则后才会写下`approved`；**不是执行部署动作或证明生产安全合规**。

## 4. Docker 复现

```bash
docker compose up --build -d
docker compose exec web python -m app.bootstrap --email admin@example.com
```

然后访问 `http://localhost:8000`。

若希望改成 PostgreSQL：先安全设置 `POSTGRES_PASSWORD` 环境变量，再使用：

```bash
docker compose -f compose.yml -f compose.postgres.yml up --build -d
```

**重要**：Docker示例只用于本地开发与技术演示，不能直接暴露在公网。生产部署必须配置HTTPS反向代理、`COOKIE_SECURE=true`、登录限流、备份、迁移、监控等，见生产差距清单。

## 5. 测试

```bash
pip install -r requirements-test.txt
pytest -q
node --test tests/frontend_release.test.cjs
```

测试使用独立临时数据库，覆盖原有登录、权限、CSRF、项目隔离、工单、UAT、质量规则、CSV导出，以及演示/严格职责模式、附件上传/越权/预览、上线门禁与双人审批。**尚未完成人工浏览器UAT**。

## 6. 目录

```text
app/
  main.py            API、权限、业务规则
  models.py          数据表
  quality.py         数据质量规则
  seed.py            项目及UAT基础模板
  bootstrap.py       安全初始化管理员
  static/            HTML/CSS/JS网页
 data/
  sample_institutions.csv    12条完全虚构的异常样本（3异常）
  sample_institutions_clean.csv   12条无异常模拟样本
 docs/
  PRD.md             需求基线
  roles_RACI.md      角色与权限矩阵
  process_and_data.md 业务流程、数据字典、指标定义
  UAT.md             手工验收清单与结果记录模板
  production_gap.md  上线准入与安全差距
  sources.md         参考资料
 tests/              自动化测试
 .github/workflows/ci.yml
```

## 7. 产品设计和技术决策

* **先需求再开发**：项目隔离、角色矩阵、审批双人原则先写入文档，再做API控制。
* **统一后端校验**：按钮隐藏不代表授权；所有敏感API均验证身份、项目成员关系和角色，防止只改URL访问别的项目。
* **先封闭注册**：企业内部系统适合管理员邀请模式，不开放任何人自行注册；正式环境应改成邮件邀请/SSO与MFA。
* **先SQLite可复现**：没有付费云资源也能运行；未来迁移到PostgreSQL（须补正式迁移工具和回滚）。
* **数据最小化**：只接收六个模拟机构字段，限制每次最多1000条、字段长度和CSV大小。无患者信息。
* **工作流不可跳级**：整改负责人不能直接关闭问题；UAT的执行与验收需要分开。

## 8. 发布状态（请勿混淆）

- **本仓库代码**：v0.3.3-rc.1，后端20项、HTTP流程15项、前端提交处理2项通过；浏览器UAT和GitHub发布待完成。
- **此前 Sites 私人网址**：是旧前端原型，未因本包的生成自动更新。
- **公网生产上线**：未实施；不应宣称完成渗透测试、运维SLA或真实企业客户验证。

## 9. 当前五步实施状态

见 `docs/PROJECT_STATUS.md`，包括需由业务方确认的角色复用与UAT证据策略。

## 10. 作者与贡献披露

这是面向个人学习与求职的模拟企业业务系统。代码实现采用AI辅助；使用者应如实区分自己亲自完成的需求评审、规则制定、UAT验证、文档修改和实际编码工作。不得将演示数据声称为医院真实生产数据。

License: MIT（见 `LICENSE`）。

## 11. GitHub与独立云部署（v0.3.1新增）

查看 [`docs/DEPLOY_GITHUB.md`](docs/DEPLOY_GITHUB.md)。含完整GitHub初始化、Railway + PostgreSQL部署变量、持久化证据存储、账户初始化、云端验收与原站点升级的限制说明。

提供 `railway.json`、`scripts/api_smoke.py` 和 `scripts/browser_smoke.py`；CI除了`pytest`还检查前端JavaScript语法，并提供可在GitHub Actions运行的Chromium浏览器冒烟测试（目前尚未触发云端运行）。**云端发布、GitHub仓库创建以及原Sites站点升级仍待真实服务授权，不因生成文件而自动完成。**


## 12. v0.3.2本地UAT工程化

新增 `scripts/live_api_uat.py`（端到端真实HTTP角色流程验证）、`scripts/browser_uat.py`（真实Chromium页面操作，待在允许浏览器访问本地服务的环境中执行）、`scripts/start_local.ps1`与`scripts/stop_local.ps1`（Windows Docker启停），以及运行记录和操作指南。用户创建后，角色分配下拉框会立即更新，不必手动刷新页面。

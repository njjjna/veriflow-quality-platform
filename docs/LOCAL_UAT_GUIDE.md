# VeriFlow v0.3.2｜Windows本地运行和UAT操作手册

> 目标：不部署到公网、不上传企业真实资料，在本地完成Docker演示与用户验收。
>
> 首次执行前，**不要填入任何真实医院数据、患者信息或客户内部资料**。

## A. Windows Docker 本地启动（不需要公网服务器）

1. 安装 Docker Desktop 并启动，等待显示 Engine running；Windows设备请先满足Docker Desktop所要求的WSL2等前置条件。
2. 解压工程ZIP，打开 `veriflow-enterprise` 文件夹，在资源管理器地址栏输入 `powershell`，回车。
3. 检查 `docker compose version` 可以正常执行。
4. 在PowerShell运行：

   ```powershell
   ./scripts/start_local.ps1 -AdminEmail 'admin@demo.invalid'
   ```

5. 首次运行默认使用**本地PostgreSQL**。脚本会生成随机数据库密码，写入工程根目录的`.env`文件（Git会忽略它）。如果只想用SQLite，请在启动和停止命令中都添加 `-UseSQLite`。
6. 终端提示设置至少12位管理员密码并重复输入。请自行保管，**不要发给AI或放进GitHub**。
7. 浏览器中打开 `http://localhost:8000`，用上一步的邮箱和密码登录。
8. 后续启动已有系统时：

   ```powershell
   ./scripts/start_local.ps1 -NoBootstrap
   ```

9. 停止但保留数据： `./scripts/stop_local.ps1`。不要执行 `docker compose down -v`，除非你明确想删除全部本地演示数据。

> 若PowerShell拒绝本地脚本执行，可以不修改全局安全策略，直接在`-UseSQLite`简化模式逐行运行 `docker compose up --build -d`、`docker compose exec web python -m app.bootstrap --email admin@demo.invalid`；如采用默认PostgreSQL，需先在`.env`设置随机密码并用`docker compose -f compose.yml -f compose.postgres.yml`前缀代替`docker compose`，再在浏览器访问本机网址。已有管理员时无需重复bootstrap。

## B. 业务侧人工UAT（你来验收）

在管理员登录后，依次完成以下真实操作（用 `docs/UAT.md` 中编号记录预期与实际结果）：

1. **账号与权限（TC01–TC05）**：创建5个演示账户；每个账户按 `manager`、`tester`、`implementer`、`approver`、`viewer` 分配角色。记录账号创建界面截图（**不得包含临时密码**）。使用不同浏览器无痕窗口分别登录。只读用户不应看到创建工单操作。
2. **数据检查（TC09–TC10，TC29）**：在「数据质量」载入12行异常样本并执行，预期3条异常与75%通过率；转工单两次，第二次应跳过3条重复工单。测试结束前另行执行12行合格样本检查，预期0异常。
3. **整改闭环（TC06–TC08）**：测试员创建高优先级工单，经理分配整改人；整改人写整改说明后提交待复测；只能由测试员独立复测并关闭。
4. **UAT与证据（TC11–TC13，TC21–TC24）**：测试员执行验收并填写文字记录，上传一张自己生成的**模拟**PNG截图；验收负责人另行登录后批准。验证超5MB、错误格式、跨项目用户访问被拒绝。
5. **CSV导出（TC14–TC15）**：在Chrome/Edge点击「另存为/导出CSV」，测试保存位置选择；关闭或不支持该功能时，验证普通下载可在浏览器下载记录中找到，CSV编码正确。
6. **上线质量门禁（TC25–TC27）**：未关闭高优先级工单或未审完UAT时应阻止上线；清理阻断事项后由项目经理提交、验收负责人独立批准。
7. **重启与持久化（TC28）**：停止/重新启动Docker容器，确认工单、用户、附件仍保留（不要删除数据卷）。

记录每条用例的状态：**通过/失败/阻断/未执行**。保留无敏感信息的截图，失败时写BUG编号。不要把「自动化测试通过」当成「人工UAT通过」。

## C. 自动HTTP集成验收（会修改演示数据）

该项可在本机Python 3.11+环境执行；Docker内运行也可以。建议针对单独的测试数据库而非你准备展示的数据库。

```powershell
pip install -r requirements.txt
$env:VERIFLOW_UI_URL='http://127.0.0.1:8000'
$env:VERIFLOW_UI_EMAIL='admin@demo.invalid'
$env:VERIFLOW_UI_PASSWORD=Read-Host '输入本机测试管理员密码'
python scripts/live_api_uat.py
```

注意：测试运行会创建5个虚构测试用户、工单和审批记录；如果不想污染展示数据，请先复制项目并配置独立 `DATABASE_URL`/挂载卷。

## D. Playwright真实浏览器自动UAT

在本机另建Python环境、安装依赖：

```powershell
pip install -r requirements.txt playwright
python -m playwright install chromium
$env:VERIFLOW_UI_URL='http://127.0.0.1:8000'
$env:VERIFLOW_UI_EMAIL='admin@demo.invalid'
$env:VERIFLOW_UI_PASSWORD=Read-Host '输入本机测试管理员密码'
python scripts/browser_smoke.py
python scripts/browser_uat.py
```

成功后在本地生成 `test-artifacts/` 中的截图、CSV及测试摘要。`test-artifacts/` 已在Git忽略清单中，避免把偶然涉及账号信息的截图自动公开。

本脚本验证：登录、管理员创建账号及分配角色、首次改密、异常数据检查、去重转工单、新增工单、CSV下载、UAT执行与独立审批、上线门禁页面和浏览器JavaScript错误。

**仍需你亲自执行：** 系统保存文件对话框（Chrome/Edge版本差异）、多浏览器兼容、无障碍及完整29项业务手工验收。

## E. GitHub工程化（可选；不等于公网部署）

GitHub可以只用于源代码、PRD、自动化测试，不需要配置Railway或线上数据库。先创建私有空仓库 `veriflow-quality-platform`，之后在工程根目录执行：

```powershell
git init
git add .
git commit -m "feat: reproducible local VeriFlow v0.3.2 with UAT"
git branch -M main
git remote add origin https://github.com/njjjna/veriflow-quality-platform.git
git push -u origin main
```

请使用GitHub授权管理器或浏览器授权，不要向聊天或仓库粘贴Personal Access Token。GitHub Actions可运行单元和Chromium浏览器测试；Actions运行结果只有实际成功后才算通过。

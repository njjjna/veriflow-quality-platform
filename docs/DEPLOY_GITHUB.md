# GitHub + Railway 独立部署实施手册（v0.3.1）

> 本手册是**待执行的部署步骤**，不能替代云端实际成功部署的证据。**不得将源码中的演示数据称为真实医院数据**。平台与数据库可能收费，确认报价后再创建云服务。

## A. GitHub 独立仓库

1. 登录 GitHub，创建一个空仓库，建议名称 `veriflow-quality-platform`，**不要选择**自动初始化 README / LICENSE / gitignore（本项目已有）。如果计划公开，先审查文件无口令、患者记录或客户资料。
2. 将当前文件夹解压到电脑后打开终端，在包含 `README.md` 的项目根目录执行：

```bash
git init
git branch -M main
git add .
git commit -m "feat: VeriFlow v0.3.1 enterprise workflow MVP"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/veriflow-quality-platform.git
git push -u origin main
```

3. GitHub → Actions → 检查 `API and static checks` 的结果。不得在Actions日志中打印任何管理员密码。
4. 使用第二台电脑从这个新仓库 `git clone`，照 `README.md` 运行并验证12行模拟数据、3条异常，留存复现证据。

**工具限制说明**：只有对已有仓库的读写权限，不代表可以自动替用户创建新的GitHub仓库。若尚未创建，请先完成第1步；不要把代码推到其他不相关的仓库。

## B. 独立上线：Railway 示例（可替代为Render或自建主机）

Railway 可部署Dockerfile应用并连接托管 PostgreSQL。费用按服务当前报价计算；没有授权不应代用户付费。

1. Railway创建项目 → 新建 PostgreSQL 服务（用模拟数据专库，禁止混用实际业务库）。
2. 为后端新建 GitHub Repo 服务，连接刚创建的仓库。`railway.json` 指定Docker构建和健康检查。
3. 在应用服务的 Variables 中设置：

| 变量 | 值与要求 |
| --- | --- |
| `DATABASE_URL` | 通过Railway变量引用绑定Postgres连接字符串，**不要提交到Git**；支持`postgresql://`及`postgres://`形式 |
| `VERIFLOW_MODE` | `demo` 供隔离演示测试；`production` 为单人单项目单角色策略（不代表已做生产安全审计） |
| `COOKIE_SECURE` | `true`；站点必须由HTTPS访问 |
| `ALLOWED_ORIGIN` | 填入最终站点HTTPS origin，例如 `https://your-project.up.railway.app`（应用CSRF原点限制） |
| `VERIFLOW_UPLOAD_DIR` | `/data/uploads`，必须给服务挂载持久卷至`/data`并确认写权限 |
| `PORT` | 由平台提供或留空；Docker启动命令自动读取该变量 |

4. 给应用服务添加Volume并挂载到`/data`，确认容器使用 UID 10001 可以写入，否则附件会失败。也可改成私有对象存储，但需先实现对应后端适配。
5. 使用Railway控制台/CLI连接运行中的应用容器，运行 `python -m app.bootstrap --email <你的管理员邮箱>`，交互设置不少于12位、唯一的管理员密码。不要把管理员密码放进GitHub源码、README或CI环境日志。`railway ssh`可进入容器，具体命令以平台界面 **Copy SSH Command** 为准。
6. 在Railway项目设置中添加生成的公网域名。确认HTTPS可访问且 `/api/health` 返回 `status=ok`。
7. 在授权环境执行 `VERIFLOW_UI_URL=https://你的域名 python scripts/api_smoke.py`，使用不同角色执行UAT；之后执行浏览器脚本（需要测试账号、Playwright及Chromium）：

```bash
pip install playwright
python -m playwright install chromium
VERIFLOW_UI_URL=https://your-domain VERIFLOW_UI_EMAIL=tester@demo.invalid VERIFLOW_UI_PASSWORD='YOUR_TEST_ACCOUNT_PASSWORD' python scripts/browser_smoke.py
```

8. 上线前明确权限隔离、登录限流、备份与恢复演练、证据保留政策、文件扫描、审计日志存储，以及成本与资源停机策略。**现有版本不满足正式企业生产环境安全上线的门槛**。

## C. 如何更新原 ChatGPT Sites 演示网址

当前 `https://veriflow-niejing-2026.prettydingo8.chatgpt.site` 是**另一套、受限访问的前端原型**，并不托管本FastAPI应用，也不共享数据库。必须取得原站点可编辑权限/源码并使用支持的发布流程，才能更新其页面；不能简单向其中复制HTML就获得本版Python后端。

推荐把原页面作为历史原型或添加“最新独立演示地址”提示，并把最终独立网址放在GitHub README里。只有在实际发布完成并检查线上域名后，才将状态改为“已更新”。

## D. 发布验收证据（填写）

| 检查项 | 结果 | 证据 |
|---|---|---|
| GitHub独立仓库存在 | 待验证 | URL / 提交哈希 |
| GitHub Actions测试成功 | 待验证 | Workflow URL |
| 公网HTTPS访问 | 待验证 | 独立域名 |
| 数据库重启后数据保留 | 待验证 | 前后截图/记录 |
| 两个独立用户同时操作 | 待验证 | 审计日志 |
| 证据附件上传/受控下载 | 待验证 | UAT TC21–TC24 |
| demo无患者真实信息 | 设计要求 | 样本字典与审核记录 |
| 发布版本和源码同一提交 | 待验证 | Git Commit SHA |

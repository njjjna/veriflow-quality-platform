"""Playwright browser acceptance for a running local VeriFlow *demo* database.

Unlike pure API tests, this exercises real page forms, JavaScript, uploads, and CSV
browser download. Test user accounts and tickets are automatically added to the
specified disposable demo database; never run against real data.

Environment: VERIFLOW_UI_URL, VERIFLOW_UI_EMAIL, VERIFLOW_UI_PASSWORD,
optional VERIFLOW_CHROMIUM_PATH (system Chromium rather than Playwright browser).
"""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import sys
import uuid
from playwright.sync_api import sync_playwright, expect

URL=os.environ['VERIFLOW_UI_URL'].rstrip('/')
EMAIL=os.environ['VERIFLOW_UI_EMAIL']
PASS=os.environ['VERIFLOW_UI_PASSWORD']
PATH=Path(os.getenv('VERIFLOW_SCREENSHOT_DIR','./test-artifacts')).resolve()
PATH.mkdir(parents=True,exist_ok=True)
RESULTS=[]


def ok(name):
    RESULTS.append(name)
    print(f'BROWSER PASS {len(RESULTS):02d}: {name}')


def nav(page, label):
    page.locator('#nav').get_by_role('button',name=label,exact=True).click()
    headings={'总览':'质量总览','用户与权限':'用户与项目权限',
              '数据质量':'数据质量检查','问题工单':'问题与整改工单',
              'UAT验收':'UAT用户验收测试','上线审批':'上线审批与质量门禁',
              '审计日志':'项目审计日志'}
    expect(page.get_by_role('heading',name=headings[label],exact=True)).to_be_visible()


def login(page,email,password):
    page.goto(URL,wait_until='domcontentloaded')
    expect(page.get_by_role('heading',name='欢迎使用 VeriFlow')).to_be_visible()
    page.locator('#email').fill(email)
    page.locator('#pass').fill(password)
    page.get_by_role('button',name='登录工作台').click()


def run():
    if not URL.startswith(('http://localhost:','http://127.0.0.1:')):
        raise RuntimeError('仅允许本机演示环境进行自动浏览器UAT')
    with sync_playwright() as p:
        options={'headless':True}
        if os.getenv('VERIFLOW_CHROMIUM_PATH'):
            options['executable_path']=os.environ['VERIFLOW_CHROMIUM_PATH']
            options['args']=['--no-sandbox']
        browser=p.chromium.launch(**options)
        try:
            admin_ctx=browser.new_context(viewport={'width':1400,'height':900},accept_downloads=True)
            # Use browser downloads for deterministic CI: native SaveFilePicker cannot be
            # automated cross-platform; it remains a manual UAT test item.
            admin_ctx.add_init_script('delete window.showSaveFilePicker;')
            admin=admin_ctx.new_page()
            js_errors=[]
            admin.on('pageerror',lambda e: js_errors.append(str(e)))
            login(admin,EMAIL,PASS)
            expect(admin.get_by_role('heading',name='质量总览')).to_be_visible()
            admin.screenshot(path=str(PATH/'01_dashboard.png'),full_page=True)
            ok('真实页面登录并呈现项目总览')
            nav(admin,'用户与权限')
            expect(admin.get_by_role('heading',name='用户与项目权限')).to_be_visible()
            suffix=uuid.uuid4().hex[:10]
            tester_email=f'browser-uat-{suffix}@demo.invalid'
            admin.locator('#username').fill('浏览器UAT测试员')
            admin.locator('#useremail').fill(tester_email)
            admin.get_by_role('button',name='创建临时账号').click()
            expect(admin.locator('#temp-pass')).not_to_be_empty()
            temp=admin.locator('#temp-pass').inner_text()
            assert tester_email in admin.locator('#memberuser').inner_text()
            admin.locator('#memberrole').select_option('tester')
            admin.get_by_role('button',name='保存项目角色').click()
            expect(admin.locator('#toast')).to_contain_text('已更新')
            ok('管理员使用页面创建账号并立即分配测试角色')
            ctx=browser.new_context(viewport={'width':1400,'height':900},accept_downloads=True)
            ctx.add_init_script('delete window.showSaveFilePicker;')
            page=ctx.new_page()
            page.on('pageerror',lambda e: js_errors.append(str(e)))
            login(page,tester_email,temp)
            expect(page.get_by_role('heading',name='首次登录安全设置')).to_be_visible()
            page.locator('#oldpass').fill(temp)
            new_pass='UAT!' + uuid.uuid4().hex + 'xy'
            page.locator('#newpass').fill(new_pass)
            page.get_by_role('button',name='修改密码并重新登录').click()
            expect(page.get_by_role('heading',name='欢迎使用 VeriFlow')).to_be_visible()
            page.locator('#email').fill(tester_email)
            page.locator('#pass').fill(new_pass)
            page.get_by_role('button',name='登录工作台').click()
            expect(page.get_by_role('heading',name='质量总览')).to_be_visible()
            ok('新用户首次登录强制修改密码并重新登录')
            # Create four further accounts using real admin forms, each with an
            # independent browser context and a single business role.
            actors={}
            for role, name in [('manager','项目经理'),('implementer','整改负责人'),
                               ('approver','验收负责人'),('viewer','只读访客')]:
                nav(admin,'用户与权限')
                email=f'browser-{role}-{suffix}@demo.invalid'
                admin.locator('#username').fill('浏览器UAT'+name)
                admin.locator('#useremail').fill(email)
                admin.get_by_role('button',name='创建临时账号').click()
                expect(admin.locator('#temp-pass')).not_to_be_empty()
                temporary=admin.locator('#temp-pass').inner_text()
                admin.locator('#memberrole').select_option(role)
                admin.get_by_role('button',name='保存项目角色').click()
                expect(admin.locator('#toast')).to_contain_text('已更新')
                actor_ctx=browser.new_context(viewport={'width':1400,'height':900},accept_downloads=True)
                actor_ctx.add_init_script('delete window.showSaveFilePicker;')
                actor=actor_ctx.new_page()
                actor.on('pageerror',lambda e: js_errors.append(str(e)))
                login(actor,email,temporary)
                expect(actor.get_by_role('heading',name='首次登录安全设置')).to_be_visible()
                password='UAT!' + uuid.uuid4().hex + 'xy'
                actor.locator('#oldpass').fill(temporary)
                actor.locator('#newpass').fill(password)
                actor.get_by_role('button',name='修改密码并重新登录').click()
                expect(actor.get_by_role('heading',name='欢迎使用 VeriFlow')).to_be_visible()
                login(actor,email,password)
                expect(actor.get_by_role('heading',name='质量总览')).to_be_visible()
                actors[role]=actor
            manager,fixer,approver,viewer=(actors[r] for r in ('manager','implementer','approver','viewer'))
            ok('页面创建五种业务角色，首次改密及独立会话均完成')
            nav(viewer,'问题工单')
            expect(viewer.locator('#issue-form')).to_have_count(0)
            nav(viewer,'数据质量')
            expect(viewer.get_by_role('button',name='执行质量检查',exact=True)).to_have_count(0)
            nav(viewer,'UAT验收')
            expect(viewer.locator('.uat-execute,.uat-review')).to_have_count(0)
            ok('只读账号看不到创建工单、执行检查和UAT写入入口')
            nav(manager,'上线审批')
            expect(manager.get_by_role('button',name='提交审批',exact=True)).to_be_disabled()
            manager.screenshot(path=str(PATH/'05_release_blocked.png'),full_page=True)
            ok('UAT和质量检查未完成时，页面禁止提交上线审批')
            nav(page,'数据质量')
            page.get_by_role('button',name='载入12行异常样本').click()
            expect(page.locator('#csv-note')).to_contain_text('12 行')
            page.get_by_role('button',name='执行质量检查').click()
            expect(page.locator('#quality-result')).to_contain_text('异常记录 3')
            page.screenshot(path=str(PATH/'02_quality.png'),full_page=True)
            page.get_by_role('button',name='将异常转成整改工单').click()
            expect(page.locator('#toast')).to_contain_text('新建工单 3 条')
            ok('浏览器载入12条模拟数据，检查3条异常并转工单')
            page.get_by_role('button',name='将异常转成整改工单').click()
            expect(page.locator('#toast')).to_contain_text('跳过重复 3 条')
            ok('重复运行不会重复建立同源异常工单')
            nav(page,'问题工单')
            new_title='浏览器UAT新增工单-'+suffix
            page.locator('#title').fill(new_title)
            page.locator('#description').fill('模拟系统问题：接口在异常网络条件下发生响应超时')
            page.locator('#severity').select_option('high')
            page.locator('#owner').select_option(label='浏览器UAT整改负责人 · 整改负责人')
            page.get_by_role('button',name='创建整改工单').click()
            expect(page.get_by_text(new_title,exact=True)).to_be_visible()
            page.screenshot(path=str(PATH/'03_issues.png'),full_page=True)
            ok('通过真实表单新增质量问题并在工单列表出现')
            row=page.locator('tbody tr').filter(has_text=new_title)
            row.locator('input[type=file]').set_input_files(str(PATH/'01_dashboard.png'))
            expect(page.locator('#toast')).to_contain_text('已保存证据')
            row=page.locator('tbody tr').filter(has_text=new_title)
            with page.expect_popup() as opened:
                row.get_by_role('link',name='01_dashboard.png',exact=True).click()
            preview=opened.value
            preview.wait_for_load_state('load')
            expect(preview.locator('img')).to_be_visible()
            assert preview.locator('img').evaluate('(img)=>img.naturalWidth')>0
            preview.close()
            ok('通过页面上传模拟截图并在授权浏览器窗口预览')
            nav(fixer,'问题工单')
            fixing=fixer.locator('tbody tr').filter(has_text=new_title)
            fixing.get_by_role('button',name='处理',exact=True).click()
            expect(fixer.locator('tbody tr').filter(has_text=new_title)).to_contain_text('整改中')
            fixer.once('dialog',lambda d:d.accept('已修复模拟接口超时，证据编号 FIX-001'))
            fixer.locator('tbody tr').filter(has_text=new_title).get_by_role('button',name='处理',exact=True).click()
            expect(fixer.locator('tbody tr').filter(has_text=new_title)).to_contain_text('待复测')
            def retest_dialog(d):
                if d.type=='confirm':d.accept()
                else:d.accept('独立复测模拟接口通过，证据编号 RETEST-001')
            fixer.on('dialog',retest_dialog)
            fixer.locator('tbody tr').filter(has_text=new_title).get_by_role('button',name='处理',exact=True).click()
            expect(fixer.locator('#toast')).to_contain_text('不能复测自己的工单')
            fixer.remove_listener('dialog',retest_dialog)
            ok('整改账号处理工单后提交复测；服务端拒绝自行复测')
            nav(page,'问题工单')
            page.on('dialog',retest_dialog)
            page.locator('tbody tr').filter(has_text=new_title).get_by_role('button',name='处理',exact=True).click()
            expect(page.locator('tbody tr').filter(has_text=new_title)).to_contain_text('已关闭')
            page.remove_listener('dialog',retest_dialog)
            page.screenshot(path=str(PATH/'06_issue_closed.png'),full_page=True)
            ok('独立测试账号通过真实页面复测并关闭高风险工单')
            with page.expect_download(timeout=15000) as dl:
                page.locator('#export').click()
            download=dl.value
            filepath=PATH/download.suggested_filename
            download.save_as(filepath)
            contents=filepath.read_bytes().decode('utf-8-sig')
            assert new_title in contents and 'title,severity,status' in contents
            ok('浏览器触发CSV下载，并核对文件内容（默认下载回退模式）')
            nav(page,'UAT验收')
            first=page.locator('.uat').first
            page.once('dialog',lambda dialog:dialog.accept('模拟UAT执行记录：步骤和测试截图编号 UAT-001'))
            first.get_by_role('button',name='测试通过').click()
            expect(page.locator('.uat').first).to_contain_text('待验收')
            page.screenshot(path=str(PATH/'04_uat_pending.png'),full_page=True)
            ok('真实页面执行UAT并进入独立验收待审状态')
            nav(approver,'UAT验收')
            approver.once('dialog',lambda dialog:dialog.accept('独立审核模拟UAT记录'))
            approver.locator('.uat').first.get_by_role('button',name='验收通过',exact=True).click()
            expect(approver.locator('.uat').first).to_contain_text('已验收')
            ok('不同账号进行UAT审核')
            for index in range(1,8):
                page.once('dialog',lambda dialog:dialog.accept('模拟UAT执行证据：按步骤检查，记录 UI-UAT-001'))
                page.locator('.uat').nth(index).get_by_role('button',name='测试通过',exact=True).click()
                expect(page.locator('.uat').nth(index)).to_contain_text('待验收')
            nav(approver,'UAT验收')
            for index in range(1,8):
                approver.once('dialog',lambda dialog:dialog.accept('验收负责人独立核对模拟执行证据'))
                approver.locator('.uat').nth(index).get_by_role('button',name='验收通过',exact=True).click()
                expect(approver.locator('.uat').nth(index)).to_contain_text('已验收')
            approver.screenshot(path=str(PATH/'07_all_uat_accepted.png'),full_page=True)
            ok('八项UAT全部由测试账号执行，再由验收账号独立审核')
            nav(manager,'上线审批')
            expect(manager.get_by_role('button',name='提交审批',exact=True)).to_be_disabled()
            expect(manager.locator('#app')).to_contain_text('异常')
            ok('即使八项UAT已通过，异常数据仍阻止上线申请')
            nav(page,'数据质量')
            page.get_by_role('button',name='载入12行合格样本').click()
            expect(page.locator('#csv-note')).to_contain_text('12 行')
            page.get_by_role('button',name='执行质量检查').click()
            expect(page.locator('#quality-result')).to_contain_text('异常记录 0')
            nav(manager,'上线审批')
            expect(manager.get_by_role('button',name='提交审批',exact=True)).to_be_enabled()
            for checkbox in manager.locator('#release-form input[type=checkbox]').all():checkbox.check()
            manager.locator('#release-evidence').fill('SIMULATED-SEC-001 / SIMULATED-RESTORE-001 / UI-UAT-001')
            manager.locator('#release-residual').fill('模拟遗留中低风险工单由项目经理跟进，本次仅为流程演示。')
            manager.get_by_role('button',name='提交审批',exact=True).click()
            expect(manager.locator('#app')).to_contain_text('待审核')
            manager.screenshot(path=str(PATH/'08_release_submitted.png'),full_page=True)
            ok('合格样本解除门禁；经理勾选五项确认后页面成功提交')
            nav(approver,'上线审批')
            approver.locator('#release-review-notes').fill('独立审核模拟证据与遗留问题，流程演示验收通过。')
            approver.get_by_role('button',name='批准流程',exact=True).click()
            expect(approver.locator('#app')).to_contain_text('流程批准')
            approver.screenshot(path=str(PATH/'09_release_approved.png'),full_page=True)
            ok('另一名验收负责人在页面审核上线申请，显示流程批准')
            nav(manager,'审计日志')
            expect(manager.locator('#app')).to_contain_text('review_release')
            manager.screenshot(path=str(PATH/'10_audit.png'),full_page=True)
            ok('页面审计日志可追溯上线审核事件')
            page.set_viewport_size({'width':390,'height':844})
            nav(page,'总览')
            expect(page.get_by_role('heading',name='质量总览',exact=True)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path=str(PATH/'11_mobile_dashboard.png'),full_page=True)
            ok('390px窄屏总览可见且无整页横向溢出')
            page.locator('#logout').click()
            expect(page.get_by_role('heading',name='欢迎使用 VeriFlow')).to_be_visible()
            page.reload()
            expect(page.get_by_role('heading',name='欢迎使用 VeriFlow')).to_be_visible()
            ok('退出并刷新后保持未登录状态')
            assert not js_errors, 'JavaScript运行错误：'+'; '.join(js_errors)
            ok('业务操作过程中无未捕获的JavaScript pageerror')
            report=PATH/'browser_automatic_uat.md'
            report.write_text('# VeriFlow Chromium UI自动UAT\n\n' +
                '\n'.join(f'- [x] B{i:02d} {k}' for i,k in enumerate(RESULTS,1))+
                '\n\n> 原生另存为弹窗、其他浏览器、其他窄屏页面及完整可访问性仍需人工验收。\n',encoding='utf-8')
            (PATH/'browser_result.json').write_text(json.dumps({'status':'passed','count':len(RESULTS),'cases':RESULTS},ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'BROWSER UAT: {len(RESULTS)}/{len(RESULTS)} PASS')
        except Exception:
            for name,pg in [('admin_fail',locals().get('admin')),('user_fail',locals().get('page'))]:
                try:
                    if pg:pg.screenshot(path=str(PATH/f'{name}.png'),full_page=True,mask=[pg.locator('input[type=password]'),pg.locator('#temp-pass')])
                except Exception:pass
            (PATH/'browser_result.json').write_text(json.dumps({'status':'failed','passed_cases':RESULTS},ensure_ascii=False,indent=2),encoding='utf-8')
            raise
        finally:browser.close()

if __name__=='__main__':
    try:run()
    except Exception as e:
        print(f'BROWSER UAT FAILED: {e}',file=sys.stderr)
        raise

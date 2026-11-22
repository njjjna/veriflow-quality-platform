"""VeriFlow multi-user integration acceptance over a running *local TEST* HTTP server.

This script creates synthetic users and a synthetic issue. It modifies the configured
DATABASE. Run it only against a fresh disposable development database, never
against a real organization or populated personal workspace.

Usage:
  VERIFLOW_UI_URL=http://127.0.0.1:8000 \
  VERIFLOW_UI_EMAIL=admin@demo.invalid \
  VERIFLOW_UI_PASSWORD=<locally configured password> \
  python scripts/live_api_uat.py

Passwords are never written to reports. A passing HTTP test is not browser UAT.
"""
from __future__ import annotations
import csv
import io
import os
from pathlib import Path
import secrets
import sys
import uuid
import httpx

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv('VERIFLOW_UI_URL', 'http://127.0.0.1:8000').rstrip('/')
ADMIN = os.environ['VERIFLOW_UI_EMAIL']
ADMIN_PW = os.environ['VERIFLOW_UI_PASSWORD']
if not URL.startswith(('http://127.0.0.1:', 'http://localhost:')):
    raise SystemExit('安全限制：集成脚本仅允许连接本机测试服务。')
RESULTS: list[str] = []


def pass_case(label: str):
    RESULTS.append(label)
    print(f'PASS {len(RESULTS):02d} | {label}')


def require(r: httpx.Response, expected=200):
    assert r.status_code == expected, f'{r.request.method} {r.request.url.path}: expected {expected}, got {r.status_code}, body={r.text[:260]}'
    return r.json() if r.headers.get('content-type', '').startswith('application/json') else r


class Actor:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.http = httpx.Client(base_url=URL, timeout=25, follow_redirects=False, trust_env=False)
        self.csrf = ''

    def login(self):
        d = require(self.http.post('/api/auth/login', json={'email':self.email, 'password':self.password}))
        self.csrf = d['csrf_token']
        return d

    def get(self, path: str):
        return self.http.get(path)

    def post(self, path: str, obj=None, files=None):
        kw = {'headers': {'X-CSRF-Token': self.csrf}}
        if files is None: kw['json'] = obj
        else: kw['files'] = files
        return self.http.post(path, **kw)

    def close(self): self.http.close()


def run():
    actors=[]
    try:
        r=httpx.get(URL+'/api/health',timeout=10,trust_env=False)
        assert require(r)['status']=='ok'
        assert r.json()['mode'] == 'demo', '此集成示例要求隔离的demo模式数据库'
        pass_case('服务健康，使用本机演示数据库')
        require(httpx.get(URL+'/api/projects',timeout=10,trust_env=False),401)
        pass_case('未登录访问项目接口被拒绝（401）')
        admin=Actor(ADMIN, ADMIN_PW);actors.append(admin)
        admin.login()
        projects=require(admin.get('/api/projects'))
        assert projects
        pid=projects[0]['id']
        base=f'/api/projects/{pid}'
        pass_case('管理员登录及项目读取')

        suffix=uuid.uuid4().hex[:10]
        ids={}
        for role in ('manager','tester','implementer','approver','viewer'):
            email=f'uat-{role}-{suffix}@demo.invalid'
            user=require(admin.post('/api/admin/users', {'email':email,'name':f'UAT {role}'}),201)
            ids[role]=user['id']
            require(admin.post(base+'/members', {'user_id':user['id'],'role':role}))
            actor=Actor(email,user['temporary_password']);actors.append(actor)
            info=actor.login()
            assert info['must_change_password']
            assert actor.get('/api/projects').status_code == 403
            new_password='UATonly!' + secrets.token_urlsafe(17)
            require(actor.post('/api/auth/change-password',{'old_password':actor.password,'new_password':new_password}))
            actor.password=new_password
            assert actor.login()['must_change_password'] is False
            ids[role+'_actor']=actor
        pass_case('管理员建5种角色账户；首次登录强制改密码；不同会话生效')
        mgr=ids['manager_actor']; tester=ids['tester_actor']; fixer=ids['implementer_actor']; auditor=ids['approver_actor']; viewer=ids['viewer_actor']
        assert viewer.post(base+'/issues', {'title':'viewer should not write'}).status_code==403
        pass_case('只读用户不可创建工单（403）')

        issue=require(tester.post(base+'/issues', {'title':f'UAT高优先级接口异常{suffix}', 'severity':'high','description':'模拟医院接口异常：请求等待超时','assignee_id':ids['implementer']}),201)
        iid=issue['id']
        pass_case('测试人员创建高风险工单并指派整改人')

        # Valid small PNG: only synthetic image bytes, no screenshots or personal data.
        png=(b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' +
             b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89' +
             b'\x00\x00\x00\x0bIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\xa5\xf6E@' +
             b'\x00\x00\x00\x00IEND\xaeB`\x82')
        attachment=require(tester.post(base+f'/attachments/issue/{iid}', files={'upload':('proof.png',png,'image/png')}),201)
        aid=attachment['id']
        assert require(tester.get(base+f'/attachments/{aid}/file?preview=true')).status_code==200
        pass_case('上传模拟图片证据；已登录用户可受控预览')

        require(fixer.post(base+f'/issues/{iid}/transition', {'target_status':'in_progress', 'notes':'整改开始'}))
        require(fixer.post(base+f'/issues/{iid}/transition', {'target_status':'ready_for_retest', 'notes':'已修复超时设置并完成模拟联调'}))
        assert fixer.post(base+f'/issues/{iid}/transition', {'target_status':'closed','notes':'不应自行复测关闭'}).status_code==403
        closed=require(tester.post(base+f'/issues/{iid}/transition', {'target_status':'closed','notes':'模拟接口复测通过，测试结果已记录'}))
        assert closed['status']=='closed'
        pass_case('整改→待复测→独立复测关闭；整改人员不可自审')

        rows=list(csv.DictReader((ROOT/'data/sample_institutions.csv').open(encoding='utf-8-sig')))
        q=require(tester.post(base+'/quality/check', {'rows':rows}))
        assert (q['total'],q['bad_count'])==(12,3)
        created=require(tester.post(base+f"/quality/{q['run_id']}/create-issues"))
        duplicate=require(tester.post(base+f"/quality/{q['run_id']}/create-issues"))
        assert created['created']==3 and duplicate['created']==0
        pass_case('12条模拟数据识别3异常；重复转工单不重复创建')

        cases=require(tester.get(base+'/uat'))
        assert len(cases)==8
        for c in cases:
            require(tester.post(base+f"/uat/{c['id']}/execute", {'passed':True,'evidence':f'模拟证据 {c["code"]}：执行步骤及截图编号'}))
            assert tester.post(base+f"/uat/{c['id']}/review", {'accepted':True, 'notes':'违规自审'}).status_code==403
            require(auditor.post(base+f"/uat/{c['id']}/review", {'accepted':True, 'notes':'不同账号独立审核确认'}))
        assert all(x['status']=='accepted' for x in require(tester.get(base+'/uat')))
        pass_case('8项UAT由测试人员执行、验收人员独立审核；自审被拒绝')

        check_before=require(mgr.get(base+'/release'))
        assert any('异常' in x for x in check_before['checks']['blockers'])
        pass_case('质量存在异常时，上线审批门禁正确阻止')
        clean=list(csv.DictReader((ROOT/'data/sample_institutions_clean.csv').open(encoding='utf-8-sig')))
        clean_result=require(tester.post(base+'/quality/check', {'rows':clean}))
        assert clean_result['bad_count']==0
        passed_checks=require(mgr.get(base+'/release'))
        assert not passed_checks['checks']['blockers']
        pass_case('加载12条合格模拟数据后上线门禁解除')
        payload={k:True for k in ('security_reviewed','rollback_plan_tested','backup_restore_tested','delivery_documents_ready','operations_handover_ready')}
        payload.update(evidence_reference='SEC-DEMO-2026 / RESTORE-DEMO / UAT-REPORT',residual_risk_notes='剩余中低风险异常已标记负责人并纳入后续整改计划。')
        submitted=require(mgr.post(base+'/release',payload),201)
        assert mgr.post(base+f"/release/{submitted['id']}/review",{'accepted':True,'notes':'不允许自行审核123456'}).status_code==403
        approved=require(auditor.post(base+f"/release/{submitted['id']}/review",{'accepted':True,'notes':'模拟审批检查确认，保留后续实施记录'}))
        assert approved['status']=='approved'
        pass_case('项目经理申请，独立验收人审批；申请人不可自审')

        csv_resp=tester.get(base+'/issues.csv')
        assert csv_resp.status_code==200 and csv_resp.content.startswith(b'\xef\xbb\xbf')
        csv_text=csv_resp.content.decode('utf-8-sig')
        assert 'title,severity,status' in csv_text and issue['title'] in csv_text
        pass_case('CSV导出UTF-8-BOM正确包含工单信息')
        audit=require(mgr.get(base+'/audit'))
        assert len(audit)>10
        pass_case('审计日志能够追踪关键操作')
        n=len(RESULTS)
        print(f'API END-TO-END ACCEPTANCE: {n}/{n} PASS')
        out=os.getenv('VERIFLOW_API_REPORT')
        if out:
            path=Path(out)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('# VeriFlow 本机HTTP集成验收\n\n'
                + '\n'.join(f'- [x] TC{i:02d} {label}' for i,label in enumerate(RESULTS,1))
                + '\n\n> 注意：本次为真实HTTP/API多角色集成测试，不等于真实Chromium浏览器UAT，也不代表生产安全认证。\n', encoding='utf-8')
    finally:
        for actor in actors: actor.close()

if __name__=='__main__':
    try:run()
    except Exception as ex:
        print(f'FAIL after {len(RESULTS)} cases: {ex}',file=sys.stderr)
        raise

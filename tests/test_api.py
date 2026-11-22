import csv
from pathlib import Path
from app.models import Issue, AuditEvent
from .conftest import login


def url(fx, suffix): return f'/api/projects/{fx["project"]}{suffix}'


def test_access_without_login(fx):
    assert fx['client'].get('/api/projects').status_code == 401
    assert fx['client'].get(url(fx, '/issues.csv')).status_code == 401


def test_project_isolation(fx):
    c=fx['client']; login(fx,'viewer')
    assert c.get(url(fx,'/dashboard')).status_code == 200
    assert c.get(f'/api/projects/{fx["other_project"]}/issues').status_code == 403


def test_csrf_guard_and_readonly(fx):
    c=fx['client']; headers=login(fx,'viewer')
    payload={'title':'Test issue needed'}
    assert c.post(url(fx,'/issues'),json=payload).status_code == 403
    login(fx,'tester')
    assert c.post(url(fx,'/issues'),json=payload).status_code == 403
    assert c.post(url(fx,'/issues'),json=payload,headers=c.get('/api/auth/me').json() and {'X-CSRF-Token':c.get('/api/auth/me').json()['csrf_token']}).status_code == 201


def test_issue_workflow_separation(fx):
    c=fx['client']; h=login(fx,'tester')
    issue=c.post(url(fx,'/issues'),json={'title':'Interface latency','severity':'high','assignee_id':fx['ids']['implementer']},headers=h)
    assert issue.status_code==201, issue.text
    iid=issue.json()['id']
    assert c.post(url(fx,f'/issues/{iid}/transition'),json={'target_status':'closed','notes':'skip retest'},headers=h).status_code==409
    h=login(fx,'implementer')
    assert c.post(url(fx,f'/issues/{iid}/transition'),json={'target_status':'in_progress','notes':'start'},headers=h).status_code==200
    assert c.post(url(fx,f'/issues/{iid}/transition'),json={'target_status':'ready_for_retest','notes':'fixed and documented'},headers=h).status_code==200
    assert c.post(url(fx,f'/issues/{iid}/transition'),json={'target_status':'closed','notes':'I tested it'},headers=h).status_code==403
    h=login(fx,'tester')
    assert c.post(url(fx,f'/issues/{iid}/transition'),json={'target_status':'closed','notes':'API regression passed'},headers=h).status_code==200
    assert c.get(url(fx,'/dashboard')).json()['blocking_issues']==0
    with fx['app'].state.SessionFactory() as db:
        assert db.query(AuditEvent).filter_by(action='transition_issue').count()==3


def test_issue_cross_project_object_rejection(fx):
    c=fx['client'];h=login(fx,'admin')
    response=c.post(f'/api/projects/{fx["other_project"]}/issues',json={'title':'Other project issue'},headers=h)
    iid=response.json()['id']
    assert c.post(url(fx,f'/issues/{iid}/assign'),json={'assignee_id':fx['ids']['tester']},headers=h).status_code==404


def test_uat_tester_and_approver(fx):
    c=fx['client'];h=login(fx,'tester')
    cid=c.get(url(fx,'/uat')).json()[0]['id']
    assert c.post(url(fx,f'/uat/{cid}/execute'),json={'passed':True,'evidence':'screenshots attached #4'},headers=h).status_code==200
    assert c.post(url(fx,f'/uat/{cid}/review'),json={'accepted':True},headers=h).status_code==403
    h=login(fx,'approver')
    assert c.post(url(fx,f'/uat/{cid}/review'),json={'accepted':True,'notes':'reviewed evidence'},headers=h).status_code==200
    assert c.get(url(fx,'/dashboard')).json()['uat_accepted']==1
    h=login(fx,'tester')
    assert c.post(url(fx,f'/uat/{cid}/execute'),json={'passed':False,'evidence':'case failed #5'},headers=h).status_code==200
    assert c.get(url(fx,'/dashboard')).json()['uat_accepted']==0


def test_quality_and_dedup(fx):
    c=fx['client'];h=login(fx,'tester')
    path=Path(__file__).parent.parent/'data'/'sample_institutions.csv'
    with path.open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
    out=c.post(url(fx,'/quality/check'),json={'rows':rows},headers=h)
    assert out.status_code==200,out.text
    d=out.json();assert d['total']==12 and d['bad_count']==3 and d['pass_rate']==75.0
    batch=url(fx,f'/quality/{d["run_id"]}/create-issues')
    assert c.post(batch,headers=h).json()['created']==3
    assert c.post(batch,headers=h).json()['created']==0
    assert c.get(url(fx,'/dashboard')).json()['issues']==3


def test_quality_rejects_unknown_field(fx):
    c=fx['client'];h=login(fx,'tester')
    d={'institution_id':'H001','institution_name':'x','system_code':'x','status':'active','success_rate':'80','go_live_date':'2026-11-11','patient_name':'sensitive'}
    assert c.post(url(fx,'/quality/check'),json={'rows':[d]},headers=h).status_code==422


def test_admin_create_user_and_membership(fx):
    c=fx['client'];h=login(fx,'admin')
    created=c.post('/api/admin/users',json={'name':'New Member','email':'new@example.test'},headers=h)
    assert created.status_code==201
    r=created.json();assert len(r['temporary_password'])>=15
    assert c.post(url(fx,'/members'),json={'user_id':r['id'],'role':'viewer'},headers=h).status_code==200
    assert any(m['id']==r['id'] for m in c.get(url(fx,'/members')).json())
    c.post('/api/auth/logout',headers=h)
    logged=c.post('/api/auth/login',json={'email':'new@example.test','password':r['temporary_password']})
    assert logged.status_code==200
    assert c.get('/api/projects').status_code==403
    csrf=logged.json()['csrf_token']
    changed=c.post('/api/auth/change-password',json={'old_password':r['temporary_password'],'new_password':'BrandNewPassword2026!'},headers={'X-CSRF-Token':csrf})
    assert changed.status_code==200
    assert c.get('/api/auth/me').status_code==401


def test_export_is_attachment_and_formula_safe(fx):
    c=fx['client'];h=login(fx,'tester')
    c.post(url(fx,'/issues'),json={'title':'=2+2 Dangerous', 'description':'test'},headers=h)
    exported=c.get(url(fx,'/issues.csv'))
    assert exported.status_code==200
    assert exported.headers['content-disposition'].startswith('attachment;')
    assert "'=2+2" in exported.text

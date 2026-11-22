"""Regression checks for stakeholder decisions: demo multi-role / strict production, evidence and release gates."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app, PH
from app.models import User
from app.seed import new_id, make_project
from .conftest import login


def url(fx, tail):
    return f'/api/projects/{fx["project"]}{tail}'


def test_demo_combined_roles_cannot_self_approve(fx):
    c = fx['client']
    headers = login(fx, 'admin')
    r = c.post(url(fx, '/members'), json={'user_id': fx['ids']['tester'], 'role': 'tester,approver'}, headers=headers)
    assert r.status_code == 200, r.text
    assert any(m['role'] == 'approver,tester' for m in c.get(url(fx, '/members')).json() if m['id'] == fx['ids']['tester'])
    headers = login(fx, 'tester')
    case_id = c.get(url(fx, '/uat')).json()[0]['id']
    assert c.post(url(fx, f'/uat/{case_id}/execute'), headers=headers, json={'passed': True, 'evidence': 'synthetic interface test PASS'}).status_code == 200
    assert c.post(url(fx, f'/uat/{case_id}/review'), headers=headers, json={'accepted': True, 'notes': 'separate person required'}).status_code == 403
    headers = login(fx, 'approver')
    assert c.post(url(fx, f'/uat/{case_id}/review'), headers=headers, json={'accepted': True, 'notes': 'independently reviewed'}).status_code == 200


def test_production_single_role_admin_segregation(tmp_path):
    app = create_app('sqlite:///' + str(tmp_path / 'prod.db'), mode='production', upload_dir=str(tmp_path / 'uploads'))
    with app.state.SessionFactory() as db:
        admin = User(id=new_id(), email='root@example.test', name='Admin', password_hash=PH.hash('SuperStrongPass123!'), is_admin=True)
        member = User(id=new_id(), email='worker@example.test', name='Worker', password_hash=PH.hash('SuperStrongPass123!'))
        db.add_all([admin, member]); db.flush()
        p = make_project(db, 'Project Prod', admin.id)
        db.commit()
        pid = p.id; member_id = member.id
    with TestClient(app) as c:
        r = c.post('/api/auth/login', json={'email':'root@example.test', 'password':'SuperStrongPass123!'})
        headers = {'X-CSRF-Token': r.json()['csrf_token']}
        assert c.get('/api/health').json()['mode'] == 'production'
        multi = c.post(f'/api/projects/{pid}/members', headers=headers, json={'user_id':member_id, 'role':'manager,tester'})
        assert multi.status_code == 422
        one = c.post(f'/api/projects/{pid}/members', headers=headers, json={'user_id':member_id,'role':'tester'})
        assert one.status_code == 200
        assert c.post(f'/api/projects/{pid}/issues', headers=headers, json={'title':'Admin should not create'}).status_code == 403
        assert c.get(f'/api/projects/{pid}/issues').status_code == 200  # admin metadata/read scope only (known production gap)


def test_attachment_validation_and_access_control(fx):
    c = fx['client']; h = login(fx, 'tester')
    issue = c.post(url(fx,'/issues'), headers=h, json={'title':'Missing screenshot'}).json()
    aid = issue['id']
    pdf = b'%PDF-1.4\n1 0 obj <<>> endobj\n%%EOF\n'
    r = c.post(url(fx, f'/attachments/issue/{aid}'), headers=h, files={'upload':('result.pdf',pdf,'application/pdf')})
    assert r.status_code == 201, r.text
    ref = r.json()['id']
    assert r.json()['sha256']
    assert c.get(url(fx,f'/attachments/{ref}/file')).content == pdf
    assert c.get(url(fx,f'/attachments/{ref}/file?preview=true')).headers['content-disposition'].startswith('attachment;')
    bad = c.post(url(fx,f'/attachments/issue/{aid}'), headers=h, files={'upload':('script.html',b'<script>alert(1)</script>','text/html')})
    assert bad.status_code == 422
    fake = c.post(url(fx,f'/attachments/issue/{aid}'), headers=h, files={'upload':('fake.pdf',b'not a real PDF','application/pdf')})
    assert fake.status_code == 422
    too_big = c.post(url(fx,f'/attachments/issue/{aid}'), headers=h, files={'upload':('large.pdf',b'%PDF-' + b'0'*(5*1024*1024) + b'%%EOF','application/pdf')})
    assert too_big.status_code == 413
    login(fx,'viewer')
    assert c.get(url(fx,f'/attachments/{ref}/file')).status_code == 200
    viewer_headers = {'X-CSRF-Token': c.get('/api/auth/me').json()['csrf_token']}
    assert c.post(url(fx,f'/attachments/issue/{aid}'), headers=viewer_headers, files={'upload':('valid.pdf',pdf,'application/pdf')}).status_code == 403
    login(fx, 'outsider')
    assert c.get(url(fx,f'/attachments/{ref}/file')).status_code == 403
    # Attachment is not reachable from static serving.
    assert c.get('/.veriflow_uploads/'+ref).status_code == 404


def test_approved_uat_evidence_is_locked(fx):
    c=fx['client']; h=login(fx,'tester')
    cid=c.get(url(fx,'/uat')).json()[0]['id']
    assert c.post(url(fx,f'/uat/{cid}/execute'),headers=h,json={'passed':True,'evidence':'test plan case UAT-001'}).status_code==200
    h=login(fx,'approver')
    assert c.post(url(fx,f'/uat/{cid}/review'),headers=h,json={'accepted':True,'notes':'verified'}).status_code==200
    h=login(fx,'tester')
    result=c.post(url(fx,f'/attachments/uat/{cid}'),headers=h,files={'upload':('image.png',b'\x89PNG\r\n\x1a\n'+b'valid-demo','image/png')})
    assert result.status_code==409


def test_release_separation_and_recheck(fx):
    c=fx['client']; h=login(fx,'manager')
    payload={'security_reviewed':True,'rollback_plan_tested':True,'backup_restore_tested':True,
             'delivery_documents_ready':True,'operations_handover_ready':True,
             'evidence_reference':'SEC-001/RESTORE-01/UAT-001','residual_risk_notes':''}
    assert c.post(url(fx,'/release'),json=payload,headers=h).status_code==409
    # Fully verified UAT by distinct test and approval people.
    h=login(fx,'tester')
    for uat in c.get(url(fx,'/uat')).json():
        assert c.post(url(fx,f'/uat/{uat["id"]}/execute'),json={'passed':True,'evidence':'synthetic pass, #2026'},headers=h).status_code==200
        ah=login(fx,'approver')
        assert c.post(url(fx,f'/uat/{uat["id"]}/review'),json={'accepted':True,'notes':'checked'},headers=ah).status_code==200
        h=login(fx,'tester')
    row={'institution_id':'SIM-001','institution_name':'Synthetic Hospital','system_code':'API-A',
         'status':'active','success_rate':'99.9','go_live_date':'2026-11-21'}
    assert c.post(url(fx,'/quality/check'),json={'rows':[row]},headers=h).json()['bad_count']==0
    h=login(fx,'manager')
    r=c.post(url(fx,'/release'),json=payload,headers=h)
    assert r.status_code==201,r.text
    rid=r.json()['id']
    assert c.get(url(fx,'/release')).json()['requests'][0]['status']=='submitted'
    # Any new high severity issue invalidates approval even after submission.
    h=login(fx,'tester')
    issue=c.post(url(fx,'/issues'),json={'title':'New high risk item','severity':'high'},headers=h)
    assert issue.status_code==201
    h=login(fx,'approver')
    approval=c.post(url(fx,f'/release/{rid}/review'),json={'accepted':True,'notes':'reviewed all evidence'},headers=h)
    assert approval.status_code==409
    rejection=c.post(url(fx,f'/release/{rid}/review'),json={'accepted':False,'notes':'high risk issue outstanding'},headers=h)
    assert rejection.status_code==200 and rejection.json()['status']=='rejected'


def test_demo_multi_role_not_allowed_when_restarting_production(tmp_path):
    dburl = 'sqlite:///' + str(tmp_path/'modes.db')
    app = create_app(dburl, mode='demo', upload_dir=str(tmp_path/'up'))
    with app.state.SessionFactory() as db:
        u=User(id=new_id(),email='member@example.test',name='Member',password_hash=PH.hash('StrongPassword123!'))
        root=User(id=new_id(),email='admin@example.test',name='Admin',password_hash=PH.hash('StrongPassword123!'),is_admin=True)
        db.add_all([u,root]);db.flush()
        p=make_project(db,'Project Alpha',root.id)
        from app.models import Membership
        db.add(Membership(project_id=p.id,user_id=u.id,role='manager,tester'))
        db.commit()
    import pytest
    with pytest.raises(RuntimeError,match='多角色'):
        create_app(dburl, mode='production', upload_dir=str(tmp_path/'up'))


def test_release_self_approval_forbidden_in_demo_even_with_combined_roles(fx):
    """Submission and review actor must differ; role combination never overrides SoD."""
    c=fx['client']
    h=login(fx, 'admin')
    assert c.post(url(fx,'/members'), headers=h,
                  json={'user_id':fx['ids']['manager'],'role':'manager,approver'}).status_code==200
    h=login(fx, 'tester')
    uats=c.get(url(fx,'/uat')).json()
    for u in uats:
        assert c.post(url(fx,f'/uat/{u["id"]}/execute'),headers=h,
                      json={'passed':True,'evidence':'synthetic test evidence 001'}).status_code==200
        ah=login(fx,'approver')
        assert c.post(url(fx,f'/uat/{u["id"]}/review'),headers=ah,
                      json={'accepted':True,'notes':'separate reviewer'}).status_code==200
        h=login(fx,'tester')
    row={'institution_id':'SIM-001','institution_name':'Synthetic Test','system_code':'SIMSYS',
         'status':'active','success_rate':'99.9','go_live_date':'2026-11-21'}
    assert c.post(url(fx,'/quality/check'),json={'rows':[row]},headers=h).status_code==200
    h=login(fx,'manager')
    p={'security_reviewed':True,'rollback_plan_tested':True,'backup_restore_tested':True,
       'delivery_documents_ready':True,'operations_handover_ready':True,
       'evidence_reference':'SEC-123 / QA-20261121','residual_risk_notes':''}
    r=c.post(url(fx,'/release'),headers=h,json=p)
    assert r.status_code==201,r.text
    r2=c.post(url(fx,f'/release/{r.json()["id"]}/review'),headers=h,
              json={'accepted':True,'notes':'manager attempting to self approve'})
    assert r2.status_code==403


def test_image_attachment_preview_and_unauthorized_type(fx):
    from PIL import Image
    import io
    c=fx['client'];h=login(fx,'tester')
    case_id=c.get(url(fx,'/uat')).json()[0]['id']
    image = Image.new('RGB',(6,6),(255,255,255))
    buffer = io.BytesIO();image.save(buffer, format='PNG')
    data=buffer.getvalue()
    r=c.post(url(fx,f'/attachments/uat/{case_id}'),headers=h,
             files={'upload':('screenshot.png',data,'image/png')})
    assert r.status_code==201,r.text
    fileid=r.json()['id']
    preview=c.get(url(fx,f'/attachments/{fileid}/file?preview=true'))
    assert preview.status_code==200 and preview.headers['content-disposition'].startswith('inline;')
    assert preview.headers['content-type']=='image/png'
    assert preview.content==data
    # Approver is allowed to read but not change the test evidence.
    h=login(fx,'approver')
    assert c.get(url(fx,f'/attachments/{fileid}/file')).status_code==200
    assert c.post(url(fx,f'/attachments/uat/{case_id}'),headers=h,
                  files={'upload':('screenshot.png',data,'image/png')}).status_code==403

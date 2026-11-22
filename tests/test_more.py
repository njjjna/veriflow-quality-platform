from .conftest import login


def test_deactivated_user_sessions_revoked(fx):
    c=fx['client']; login(fx,'viewer'); assert c.get('/api/projects').status_code==200
    admin_headers=login(fx,'admin')
    r=c.post('/api/admin/users/'+fx['ids']['viewer']+'/deactivate',headers=admin_headers)
    assert r.status_code==200
    assert c.post('/api/auth/login',json={'email':'viewer@example.test','password':'StrongPassword123!viewer'}).status_code==401


def test_prohibit_manager_self_retest(fx):
    c=fx['client'];h=login(fx,'manager')
    iid=c.post(f'/api/projects/{fx["project"]}/issues',headers=h,
               json={'title':'manager assigned own task','assignee_id':fx['ids']['manager']}).json()['id']
    path=f'/api/projects/{fx["project"]}/issues/{iid}/transition'
    assert c.post(path,headers=h,json={'target_status':'in_progress','notes':'begin'}).status_code==200
    assert c.post(path,headers=h,json={'target_status':'ready_for_retest','notes':'fixed and checked'}).status_code==200
    assert c.post(path,headers=h,json={'target_status':'closed','notes':'manager self retest'}).status_code==403
    h=login(fx,'tester')
    assert c.post(path,headers=h,json={'target_status':'closed','notes':'independent retest passed'}).status_code==200

from uuid import uuid4
from .models import Project, UATCase

UAT_TITLES = [
    "用户登录与角色权限", "预约创建与取消", "接口调用与异常提示", "设备云端数据同步",
    "机构主数据一致性", "关键字段完整性", "安全配置与日志", "整改完成与交付确认"
]

def new_id(): return uuid4().hex

def make_project(db, name: str, admin_id: str) -> Project:
    p = Project(id=new_id(), name=name)
    db.add(p)
    db.flush()
    # Platform administrator owns provisioning, not a production business role.
    for index, title in enumerate(UAT_TITLES, start=1):
        db.add(UATCase(project_id=p.id, code=f"UAT-{index:03d}", title=title))
    db.flush()
    return p

"""Safe first-admin provisioning: interactive password entry, no default credentials."""
import argparse
import getpass
from sqlalchemy import select
from .main import app, PH
from .models import User, Project
from .seed import new_id, make_project


def main():
    parser = argparse.ArgumentParser(description="Initialize VeriFlow admin account")
    parser.add_argument("--email", required=True, help="Administrator email")
    parser.add_argument("--name", default="系统管理员")
    args = parser.parse_args()
    factory = app.state.SessionFactory
    with factory() as db:
        if db.scalar(select(User).where(User.is_admin.is_(True))):
            raise SystemExit("安全限制：已有系统管理员，拒绝重复初始化。")
        if "@" not in args.email: raise SystemExit("请填写有效邮箱")
        password = getpass.getpass("请设置管理员密码（至少12位）：")
        confirm = getpass.getpass("再次输入密码：")
        if password != confirm or len(password) < 12:
            raise SystemExit("密码不一致或长度不足")
        user = User(id=new_id(), name=args.name, email=args.email.lower().strip(),
                    password_hash=PH.hash(password), is_admin=True)
        db.add(user)
        project = make_project(db, "模拟医院系统上线质量管理项目", user.id)
        db.commit()
        print(f"已创建管理员 {user.email}，示例项目 {project.id}。未添加真实患者或客户数据。")


if __name__ == "__main__":
    main()

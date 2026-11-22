"""VeriFlow: reproducible project-scoped quality & UAT MVP. No patient data."""
from __future__ import annotations
import csv
from datetime import date, timedelta
import hashlib
import io
import json
import os
import secrets
import mimetypes
from pathlib import Path
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, HTTPException, Request, Response, Depends, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session as DBSession, sessionmaker

from .models import Base, User, SessionToken, Project, Membership, Issue, UATCase, QualityRun, AuditEvent, EvidenceAttachment, ReleaseRequest, now
from .seed import new_id, make_project
from .quality import check_rows, COLUMNS

COOKIE_NAME = "veriflow_session"
PH = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
ROLES = {"manager", "tester", "implementer", "approver", "viewer"}
STATUSES = {"open", "in_progress", "ready_for_retest", "closed"}
SEVERITIES = {"low", "medium", "high", "critical"}


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12, max_length=128)


class UserCreate(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=100)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)


class MemberCreate(BaseModel):
    user_id: str
    role: str


class IssueCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2500)
    category: str = Field(default="功能", max_length=30)
    severity: str = "medium"
    due_date: str | None = None
    assignee_id: str | None = None


class IssueTransition(BaseModel):
    target_status: str
    notes: str = Field(default="", max_length=2000)


class IssueAssign(BaseModel):
    assignee_id: str


class UATExecute(BaseModel):
    passed: bool
    evidence: str = Field(min_length=5, max_length=1000)


class UATReview(BaseModel):
    accepted: bool
    notes: str = Field(default="", max_length=1000)


class ReleaseSubmit(BaseModel):
    security_reviewed: bool
    rollback_plan_tested: bool
    backup_restore_tested: bool
    delivery_documents_ready: bool
    operations_handover_ready: bool
    evidence_reference: str = Field(min_length=12, max_length=2000)
    residual_risk_notes: str = Field(default="", max_length=2000)


class ReleaseReview(BaseModel):
    accepted: bool
    notes: str = Field(min_length=8, max_length=2000)


class QualityCheck(BaseModel):
    rows: list[dict]


def safe_cell(value: object) -> str:
    """Defend common spreadsheet formula starts. Further validation remains necessary for Excel re-save workflows."""
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def issue_info(i: Issue) -> dict:
    return {"id": i.id, "title": i.title, "description": i.description, "category": i.category,
            "severity": i.severity, "status": i.status, "assignee_id": i.assignee_id,
            "created_by": i.created_by, "created_at": i.created_at.isoformat(),
            "updated_at": i.updated_at.isoformat(), "due_date": i.due_date,
            "resolution_notes": i.resolution_notes, "retest_notes": i.retest_notes}


def uat_info(c: UATCase) -> dict:
    return {"id": c.id, "code": c.code, "title": c.title, "status": c.status,
            "executed_by": c.executed_by, "executed_at": c.executed_at.isoformat() if c.executed_at else None,
            "evidence": c.evidence, "approved_by": c.approved_by,
            "approved_at": c.approved_at.isoformat() if c.approved_at else None,
            "review_notes": c.review_notes}


def log(db: DBSession, project_id: str | None, user_id: str, action: str, kind: str, obj_id: str, detail: dict | None = None):
    db.add(AuditEvent(project_id=project_id, actor_id=user_id, action=action,
                      entity_type=kind, entity_id=str(obj_id), detail=json.dumps(detail or {}, ensure_ascii=False)))


def create_app(database_url: str | None = None, mode: str | None = None, upload_dir: str | None = None) -> FastAPI:
    mode = mode or os.environ.get("VERIFLOW_MODE", "production")
    if mode not in {"demo", "production"}:
        raise RuntimeError("VERIFLOW_MODE 必须是 demo 或 production")
    url = database_url or os.environ.get("DATABASE_URL", "sqlite:///./veriflow.db")
    # Hosted PostgreSQL providers commonly return `postgresql://`, which SQLAlchemy
    # otherwise resolves using psycopg2; this project explicitly installs psycopg v3.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    with SessionFactory() as db:
        if mode == "production" and db.scalar(select(Membership).where(Membership.role.like("%,%"))):
            raise RuntimeError("生产模式检测到已有多角色成员；须先执行数据治理，禁止直接切换模式")
    evidence_dir = Path(upload_dir or os.environ.get("VERIFLOW_UPLOAD_DIR", "./.veriflow_uploads")).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="VeriFlow", version="0.3.3-rc.1", docs_url=None, redoc_url=None)
    app.state.SessionFactory = SessionFactory
    app.state.mode = mode
    app.state.upload_dir = evidence_dir

    def get_db():
        with SessionFactory() as db:
            yield db

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response

    def auth(request: Request, db: DBSession, write: bool = False, allow_password_change: bool = False):
        token = request.cookies.get(COOKIE_NAME, "")
        if not token:
            raise HTTPException(401, "请先登录")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        s = db.get(SessionToken, token_hash)
        if not s or s.expires_at <= now():
            raise HTTPException(401, "登录已过期")
        user = db.get(User, s.user_id)
        if not user or not user.active:
            raise HTTPException(401, "账号不可用")
        if user.must_change_password and not allow_password_change:
            raise HTTPException(403, "请先修改初始密码")
        if write:
            if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), s.csrf_token):
                raise HTTPException(403, "CSRF令牌无效")
        return user, s

    def has_role(role: str, *permissions: str) -> bool:
        return bool(set(role.split(",")) & set(permissions))

    def authorized(db: DBSession, user: User, project_id: str, allowed: set[str] | None = None) -> str:
        if not db.get(Project, project_id):
            raise HTTPException(404, "项目不存在")
        if user.is_admin:
            if mode == "demo":
                return "admin"
            if allowed is not None:
                raise HTTPException(403, "生产模式下平台管理员不可兼任业务操作角色")
            return "admin"
        m = db.scalar(select(Membership).where(Membership.project_id == project_id, Membership.user_id == user.id))
        if not m:
            raise HTTPException(403, "无权访问该项目")
        if allowed is not None and not set(m.role.split(",")) & allowed:
            raise HTTPException(403, "当前角色没有此操作权限")
        return m.role

    def require_admin(user: User):
        if not user.is_admin: raise HTTPException(403, "仅系统管理员可操作")

    def validate_assignee(db: DBSession, project_id: str, assignee_id: str):
        member = db.scalar(select(Membership).where(Membership.project_id == project_id, Membership.user_id == assignee_id))
        person = db.get(User, assignee_id)
        if not person or not person.active or not member or (mode == "production" and "implementer" not in member.role.split(",")):
            raise HTTPException(422, "工单负责人必须是本项目具有整改职责的有效成员")

    @app.get("/", response_class=HTMLResponse)
    def root():
        return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    @app.get("/app.js")
    def js(): return FileResponse(Path(__file__).parent / "static" / "app.js", media_type="application/javascript")

    @app.get("/style.css")
    def css(): return FileResponse(Path(__file__).parent / "static" / "style.css", media_type="text/css")

    @app.get("/sample.csv")
    def sample_csv():
        return FileResponse(Path(__file__).parent.parent / "data" / "sample_institutions.csv", media_type="text/csv")

    @app.get("/sample-clean.csv")
    def sample_clean_csv():
        return FileResponse(Path(__file__).parent.parent / "data" / "sample_institutions_clean.csv", media_type="text/csv")

    @app.get("/api/health")
    def health(): return {"status": "ok", "version": "0.3.3-rc.1", "synthetic_only": True, "mode": mode}

    @app.post("/api/auth/login")
    def login(payload: LoginRequest, response: Response, db: DBSession = Depends(get_db)):
        user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
        try:
            good = bool(user and user.active and PH.verify(user.password_hash, payload.password))
        except (VerifyMismatchError, VerificationError):
            good = False
        if not good:
            raise HTTPException(401, "邮箱或密码错误")
        raw = secrets.token_urlsafe(48)
        csrf = secrets.token_urlsafe(32)
        db.add(SessionToken(token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                            user_id=user.id, csrf_token=csrf, expires_at=now() + timedelta(hours=12)))
        log(db, None, user.id, "login", "user", user.id)
        db.commit()
        response.set_cookie(key=COOKIE_NAME, value=raw, httponly=True,
                            secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
                            samesite="lax", max_age=12 * 3600, path="/")
        return {"id": user.id, "name": user.name, "is_admin": user.is_admin,
                "must_change_password": user.must_change_password, "csrf_token": csrf}

    @app.get("/api/auth/me")
    def me(request: Request, db: DBSession = Depends(get_db)):
        u, s = auth(request, db, allow_password_change=True)
        return {"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin,
                "must_change_password": u.must_change_password, "csrf_token": s.csrf_token}

    @app.post("/api/auth/change-password")
    def change_password(payload: ChangePasswordRequest, request: Request, response: Response,
                        db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True, allow_password_change=True)
        try:
            valid = PH.verify(user.password_hash, payload.old_password)
        except (VerifyMismatchError, VerificationError):
            valid = False
        if not valid or payload.new_password == payload.old_password:
            raise HTTPException(422, "旧密码不正确或新旧密码相同")
        user.password_hash = PH.hash(payload.new_password)
        user.must_change_password = False
        for session in db.scalars(select(SessionToken).where(SessionToken.user_id == user.id)).all():
            db.delete(session)
        log(db, None, user.id, "change_password", "user", user.id)
        db.commit()
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"message": "修改成功，请重新登录"}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
        user, s = auth(request, db, write=True, allow_password_change=True)
        db.delete(s)
        log(db, None, user.id, "logout", "user", user.id)
        db.commit()
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"message": "已退出"}

    @app.get("/api/admin/users")
    def users(request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        require_admin(user)
        return [{"id": x.id, "email": x.email, "name": x.name, "active": x.active,
                 "is_admin": x.is_admin, "must_change_password": x.must_change_password}
                for x in db.scalars(select(User).order_by(User.created_at)).all()]

    @app.post("/api/admin/users", status_code=201)
    def create_user(payload: UserCreate, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        require_admin(user)
        email = payload.email.strip().lower()
        if "@" not in email or len(email) > 254:
            raise HTTPException(422, "邮箱格式无效")
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, "用户已存在")
        temp = secrets.token_urlsafe(18)
        new_user = User(id=new_id(), email=email, name=payload.name.strip(),
                        password_hash=PH.hash(temp), must_change_password=True)
        db.add(new_user)
        log(db, None, user.id, "create_user", "user", new_user.id, {"email": email})
        db.commit()
        return {"id": new_user.id, "email": email, "temporary_password": temp,
                "notice": "临时密码仅显示一次，请通过受控渠道交付；首次登录必须修改"}

    @app.post("/api/admin/users/{uid}/deactivate")
    def deactivate_user(uid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        require_admin(user)
        target = db.get(User, uid)
        if not target: raise HTTPException(404, "用户不存在")
        if target.id == user.id: raise HTTPException(403, "管理员不可停用自己的账号")
        target.active = False
        for sess in db.scalars(select(SessionToken).where(SessionToken.user_id == uid)).all():
            db.delete(sess)
        log(db, None, user.id, "deactivate_user", "user", uid)
        db.commit()
        return {"message": "用户已停用，现有登录会话已撤销"}

    @app.get("/api/projects")
    def projects(request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        if user.is_admin:
            result = db.scalars(select(Project).order_by(Project.created_at)).all()
        else:
            result = db.scalars(select(Project).join(Membership).where(Membership.user_id == user.id)).all()
        return [{"id": x.id, "name": x.name, "industry": x.industry,
                 "role": authorized(db, user, x.id)} for x in result]

    @app.post("/api/projects", status_code=201)
    def create_project(payload: ProjectCreate, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        require_admin(user)
        project = make_project(db, payload.name, user.id)
        log(db, project.id, user.id, "create_project", "project", project.id)
        db.commit()
        return {"id": project.id, "name": project.name}

    @app.get("/api/projects/{pid}/members")
    def members(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid)
        rows = db.execute(select(Membership, User).join(User, Membership.user_id == User.id).where(Membership.project_id == pid)).all()
        return [{"id": u.id, "name": u.name, "email": u.email, "role": m.role} for m, u in rows]

    @app.post("/api/projects/{pid}/members")
    def add_member(pid: str, payload: MemberCreate, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        require_admin(user)
        authorized(db, user, pid)
        roles = sorted(set(part.strip() for part in payload.role.split(",")))
        if not roles or any(role not in ROLES for role in roles):
            raise HTTPException(422, "未知角色")
        if len(roles) > 1 and mode != "demo":
            raise HTTPException(422, "正式模式每位成员在同一项目只能有一个业务角色")
        if "viewer" in roles and len(roles) > 1:
            raise HTTPException(422, "只读角色不能与写权限角色兼任")
        canonical_role = ",".join(roles)
        target = db.get(User, payload.user_id)
        if not target or not target.active: raise HTTPException(404, "用户不存在或已停用")
        m = db.scalar(select(Membership).where(Membership.project_id == pid, Membership.user_id == target.id))
        if not m:
            m = Membership(project_id=pid, user_id=target.id, role=canonical_role)
            db.add(m)
        else:
            m.role = canonical_role
        log(db, pid, user.id, "set_member_role", "user", target.id, {"role": canonical_role, "mode": mode})
        db.commit()
        return {"message": "角色已设置"}

    def release_checks(db: DBSession, pid: str) -> dict:
        issues = db.scalars(select(Issue).where(Issue.project_id == pid)).all()
        uats = db.scalars(select(UATCase).where(UATCase.project_id == pid)).all()
        latest = db.scalar(select(QualityRun).where(QualityRun.project_id == pid).order_by(QualityRun.created_at.desc()))
        blocking = [i for i in issues if i.severity in {"high", "critical"} and i.status != "closed"]
        residual = [i for i in issues if i.severity in {"low", "medium"} and i.status != "closed"]
        blockers = []
        if blocking: blockers.append(f"尚有 {len(blocking)} 条未关闭的高/紧急问题")
        if len(uats) != 8 or any(u.status != "accepted" for u in uats):
            blockers.append("8项UAT尚未全部通过独立审核")
        if latest is None: blockers.append("尚未完成数据质量检查")
        elif latest.bad_count: blockers.append(f"最新数据检查仍有 {latest.bad_count} 条异常记录")
        return {"blockers": blockers, "residual_issues": len(residual), "latest_quality_run": latest.id if latest else None,
                "uat_accepted": sum(u.status == "accepted" for u in uats), "uat_total": len(uats)}

    def release_info(r: ReleaseRequest) -> dict:
        return {"id": r.id, "status": r.status, "requested_by": r.requested_by,
                "requested_at": r.requested_at.isoformat(), "checklist": json.loads(r.checklist_json),
                "evidence_reference": r.evidence_reference, "reviewed_by": r.reviewed_by,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "review_notes": r.review_notes}

    @app.get("/api/projects/{pid}/dashboard")
    def dashboard(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid)
        issues = db.scalars(select(Issue).where(Issue.project_id == pid)).all()
        uats = db.scalars(select(UATCase).where(UATCase.project_id == pid)).all()
        run = db.scalar(select(QualityRun).where(QualityRun.project_id == pid).order_by(QualityRun.created_at.desc()))
        blockers = [i for i in issues if i.severity in ("critical", "high") and i.status != "closed"]
        checks = release_checks(db, pid)
        current = db.scalar(select(ReleaseRequest).where(ReleaseRequest.project_id == pid).order_by(ReleaseRequest.requested_at.desc()))
        return {"issues": len(issues), "open_issues": len([i for i in issues if i.status != "closed"]),
                "blocking_issues": len(blockers), "closed_issues": len([i for i in issues if i.status == "closed"]),
                "uat_accepted": len([c for c in uats if c.status == "accepted"]), "uat_total": len(uats),
                "latest_quality": None if not run else {"total": run.total, "bad_count": run.bad_count},
                "ready_for_release": not checks["blockers"],
                "release_checklist": checks, "last_release_status": current.status if current else "none",
                "mode": mode,
                "note": "这是模拟业务的流程准入检查，不构成真实生产环境发布或安全合规批准"}

    @app.get("/api/projects/{pid}/issues")
    def list_issues(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid)
        return [issue_info(x) for x in db.scalars(select(Issue).where(Issue.project_id == pid).order_by(Issue.created_at.desc())).all()]

    @app.post("/api/projects/{pid}/issues", status_code=201)
    def create_issue(pid: str, payload: IssueCreate, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        authorized(db, user, pid, {"manager", "tester"})
        if payload.severity not in SEVERITIES: raise HTTPException(422, "严重程度无效")
        if payload.due_date:
            try:
                if date.fromisoformat(payload.due_date).isoformat() != payload.due_date: raise ValueError()
            except ValueError:
                raise HTTPException(422, "截止日期必须为YYYY-MM-DD")
        if payload.assignee_id: validate_assignee(db, pid, payload.assignee_id)
        issue = Issue(id=new_id(), project_id=pid, title=payload.title, description=payload.description,
                      category=payload.category, severity=payload.severity, due_date=payload.due_date,
                      assignee_id=payload.assignee_id, created_by=user.id)
        db.add(issue)
        log(db, pid, user.id, "create_issue", "issue", issue.id)
        db.commit()
        return issue_info(issue)

    @app.post("/api/projects/{pid}/issues/{iid}/assign")
    def assign_issue(pid: str, iid: str, payload: IssueAssign, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        authorized(db, user, pid, {"manager"})
        issue = db.get(Issue, iid)
        if not issue or issue.project_id != pid: raise HTTPException(404, "工单不存在")
        validate_assignee(db, pid, payload.assignee_id)
        issue.assignee_id = payload.assignee_id
        issue.updated_at = now()
        log(db, pid, user.id, "assign_issue", "issue", iid, {"assignee_id": payload.assignee_id})
        db.commit()
        return issue_info(issue)

    @app.post("/api/projects/{pid}/issues/{iid}/transition")
    def transition(pid: str, iid: str, payload: IssueTransition, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        role = authorized(db, user, pid)
        if user.is_admin and mode == "production":
            raise HTTPException(403, "正式模式平台管理员不得执行整改或复测")
        issue = db.get(Issue, iid)
        if not issue or issue.project_id != pid: raise HTTPException(404, "工单不存在")
        current, target = issue.status, payload.target_status
        if current == "open" and target == "in_progress":
            if mode == "production" and (not has_role(role, "implementer") or issue.assignee_id != user.id):
                raise HTTPException(403, "严格职责模式仅允许分配的整改人开始处理")
            if mode == "demo" and not has_role(role, "manager", "admin") and (not has_role(role, "implementer") or issue.assignee_id != user.id):
                raise HTTPException(403, "仅负责人或经理可开始处理")
            if not issue.assignee_id: raise HTTPException(422, "请先分配负责人")
        elif current == "in_progress" and target == "ready_for_retest":
            if mode == "production" and (not has_role(role, "implementer") or issue.assignee_id != user.id):
                raise HTTPException(403, "严格职责模式仅允许分配的整改人提交整改")
            if mode == "demo" and not has_role(role, "manager", "admin") and (not has_role(role, "implementer") or issue.assignee_id != user.id):
                raise HTTPException(403, "仅负责人或经理可提交整改")
            if len(payload.notes.strip()) < 5: raise HTTPException(422, "请填写至少5字的整改说明")
            issue.resolution_notes = payload.notes.strip()
        elif current == "ready_for_retest" and target in ("closed", "in_progress"):
            if issue.assignee_id == user.id:
                raise HTTPException(403, "整改负责人不能复测自己的工单")
            if not has_role(role, "tester") and not (mode == "demo" and has_role(role, "manager", "admin")):
                raise HTTPException(403, "仅测试人员可执行独立复测")
            if len(payload.notes.strip()) < 5: raise HTTPException(422, "请填写复测结果及证据说明")
            issue.retest_notes = payload.notes.strip()
        else:
            raise HTTPException(409, "不允许的状态流转，请按照整改-复测流程操作")
        issue.status = target
        issue.updated_at = now()
        log(db, pid, user.id, "transition_issue", "issue", iid, {"from": current, "to": target, "notes": payload.notes[:120]})
        db.commit()
        return issue_info(issue)

    @app.get("/api/projects/{pid}/uat")
    def list_uat(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid)
        return [uat_info(c) for c in db.scalars(select(UATCase).where(UATCase.project_id == pid).order_by(UATCase.code)).all()]

    @app.post("/api/projects/{pid}/uat/{cid}/execute")
    def uat_execute(pid: str, cid: int, payload: UATExecute, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        authorized(db, user, pid, {"tester"})
        c = db.get(UATCase, cid)
        if not c or c.project_id != pid: raise HTTPException(404, "UAT项不存在")
        if len(payload.evidence.strip()) < 5: raise HTTPException(422, "请填写至少5字的测试证据")
        c.status = "passed" if payload.passed else "failed"
        c.executed_by = user.id
        c.executed_at = now()
        c.evidence = payload.evidence.strip()
        c.approved_by = None
        c.approved_at = None
        c.review_notes = None
        log(db, pid, user.id, "execute_uat", "uat", str(cid), {"status": c.status})
        db.commit()
        return uat_info(c)

    @app.post("/api/projects/{pid}/uat/{cid}/review")
    def uat_review(pid: str, cid: int, payload: UATReview, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        authorized(db, user, pid, {"approver"})
        c = db.get(UATCase, cid)
        if not c or c.project_id != pid: raise HTTPException(404, "UAT项不存在")
        if c.status != "passed": raise HTTPException(409, "仅已通过执行的验收项可提交审核")
        if c.executed_by == user.id: raise HTTPException(403, "执行和验收不得由同一人完成")
        if not payload.accepted and len(payload.notes.strip()) < 5:
            raise HTTPException(422, "拒绝验收需填写原因")
        c.status = "accepted" if payload.accepted else "failed"
        c.review_notes = payload.notes
        c.approved_by = user.id
        c.approved_at = now()
        log(db, pid, user.id, "review_uat", "uat", str(cid), {"status": c.status})
        db.commit()
        return uat_info(c)

    @app.post("/api/projects/{pid}/quality/check")
    def quality_check(pid: str, payload: QualityCheck, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        authorized(db, user, pid, {"tester", "manager"})
        try:
            result = check_rows(payload.rows)
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex
        run = QualityRun(id=new_id(), project_id=pid, created_by=user.id, total=result["total"],
                         bad_count=result["bad_count"], report_json=json.dumps(result, ensure_ascii=False))
        db.add(run)
        log(db, pid, user.id, "quality_check", "quality", run.id, {"total": result["total"], "bad": result["bad_count"]})
        db.commit()
        return {"run_id": run.id, **result}

    @app.post("/api/projects/{pid}/quality/{rid}/create-issues")
    def quality_to_issues(pid: str, rid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db, write=True)
        authorized(db, user, pid, {"manager", "tester"})
        run = db.get(QualityRun, rid)
        if not run or run.project_id != pid: raise HTTPException(404, "检查批次不存在")
        result = json.loads(run.report_json)
        created = 0
        for err in result["errors"]:
            # The same data imported twice should map to the same fingerprint in one project.
            existing = db.scalar(select(Issue).where(Issue.project_id == pid, Issue.fingerprint == err["fingerprint"]))
            if existing: continue
            issue = Issue(id=new_id(), project_id=pid,
                          title=f"第{err['row']}行 · {err['rule']}",
                          description=f"机构ID: {err['institution_id'] or '空'}。规则: {err['rule']}",
                          category="数据质量", severity="medium", created_by=user.id,
                          fingerprint=err["fingerprint"])
            db.add(issue)
            created += 1
        log(db, pid, user.id, "quality_create_issues", "quality", rid, {"created": created})
        db.commit()
        return {"created": created, "skipped_duplicates": len(result["errors"])-created}

    @app.get("/api/projects/{pid}/quality/runs")
    def quality_runs(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid)
        runs = db.scalars(select(QualityRun).where(QualityRun.project_id == pid).order_by(QualityRun.created_at.desc()).limit(15)).all()
        return [{"id": x.id, "total": x.total, "bad_count": x.bad_count, "created_at": x.created_at.isoformat()} for x in runs]

    @app.get("/api/projects/{pid}/audit")
    def audit_events(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid, {"manager", "approver"})
        events = db.scalars(select(AuditEvent).where(AuditEvent.project_id == pid).order_by(AuditEvent.id.desc()).limit(100)).all()
        return [{"id": x.id, "action": x.action, "actor_id": x.actor_id,
                 "entity_type": x.entity_type, "entity_id": x.entity_id,
                 "created_at": x.created_at.isoformat()} for x in events]

    @app.get("/api/projects/{pid}/issues.csv")
    def export_issues(pid: str, request: Request, db: DBSession = Depends(get_db)):
        user, _ = auth(request, db)
        authorized(db, user, pid)
        items = db.scalars(select(Issue).where(Issue.project_id == pid).order_by(Issue.created_at)).all()
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["id", "title", "severity", "status", "assignee_id", "due_date", "resolution_notes", "retest_notes"])
        for i in items:
            writer.writerow([safe_cell(v) for v in (i.id, i.title, i.severity, i.status, i.assignee_id,
                                                   i.due_date, i.resolution_notes, i.retest_notes)])
        content = "\ufeff" + stream.getvalue()  # UTF-8 BOM for Excel Chinese display
        return StreamingResponse(iter([content.encode("utf-8")]), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="VeriFlow_issues.csv"',
                                          "Cache-Control": "no-store"})

    @app.get("/api/projects/{pid}/release")
    def release_status(pid: str, request: Request, db: DBSession = Depends(get_db)):
        u, _ = auth(request, db)
        authorized(db, u, pid)
        rows = db.scalars(select(ReleaseRequest).where(ReleaseRequest.project_id == pid).order_by(ReleaseRequest.requested_at.desc()).limit(20)).all()
        return {"checks": release_checks(db, pid), "requests": [release_info(x) for x in rows],
                "notice": "审批流程演示：不能替代上线安全评估和生产变更审批"}

    @app.post("/api/projects/{pid}/release", status_code=201)
    def submit_release(pid: str, payload: ReleaseSubmit, request: Request, db: DBSession = Depends(get_db)):
        u, _ = auth(request, db, write=True)
        authorized(db, u, pid, {"manager"})
        if not all([payload.security_reviewed, payload.rollback_plan_tested, payload.backup_restore_tested,
                    payload.delivery_documents_ready, payload.operations_handover_ready]):
            raise HTTPException(422, "安全复核、回滚、备份恢复、交付文档和运维交接均需确认")
        checks = release_checks(db, pid)
        if checks["blockers"]:
            raise HTTPException(409, "尚未满足申请条件：" + "；".join(checks["blockers"]))
        if checks["residual_issues"] and len(payload.residual_risk_notes.strip()) < 10:
            raise HTTPException(422, "尚有低/中等级遗留问题，请描述风险接受依据（至少10字）")
        pending = db.scalar(select(ReleaseRequest).where(ReleaseRequest.project_id == pid, ReleaseRequest.status == "submitted"))
        if pending: raise HTTPException(409, "已有待审核的上线申请")
        checklist = payload.model_dump(exclude={"evidence_reference"})
        record = ReleaseRequest(id=new_id(), project_id=pid, requested_by=u.id,
                                checklist_json=json.dumps(checklist, ensure_ascii=False),
                                evidence_reference=payload.evidence_reference.strip())
        db.add(record)
        log(db, pid, u.id, "submit_release", "release", record.id, {"checklist": checklist})
        db.commit()
        return release_info(record)

    @app.post("/api/projects/{pid}/release/{rid}/review")
    def review_release(pid: str, rid: str, payload: ReleaseReview, request: Request, db: DBSession = Depends(get_db)):
        u, _ = auth(request, db, write=True)
        authorized(db, u, pid, {"approver"})
        record = db.get(ReleaseRequest, rid)
        if not record or record.project_id != pid: raise HTTPException(404, "审批单不存在")
        if record.status != "submitted": raise HTTPException(409, "申请已完成审核")
        if record.requested_by == u.id:
            raise HTTPException(403, "申请与审核不能由同一人完成（包括演示兼任模式）")
        checks = release_checks(db, pid)
        if payload.accepted and checks["blockers"]:
            raise HTTPException(409, "条件发生变化，不允许批准：" + "；".join(checks["blockers"]))
        record.status = "approved" if payload.accepted else "rejected"
        record.reviewed_by = u.id
        record.reviewed_at = now()
        record.review_notes = payload.notes.strip()
        log(db, pid, u.id, "review_release", "release", rid, {"decision": record.status})
        db.commit()
        return release_info(record)

    def attachment_info(a: EvidenceAttachment) -> dict:
        return {"id": a.id, "target_type": a.target_type, "target_id": a.target_id,
                "filename": a.original_filename, "media_type": a.media_type,
                "size_bytes": a.size_bytes, "sha256": a.digest_sha256,
                "uploaded_by": a.uploaded_by, "created_at": a.created_at.isoformat()}

    def attachment_target(db: DBSession, pid: str, target_type: str, target_id: str):
        if target_type == "issue":
            obj = db.get(Issue, target_id)
        elif target_type == "uat":
            try: obj = db.get(UATCase, int(target_id))
            except ValueError: obj = None
        else:
            raise HTTPException(422, "附件对象类型无效")
        if not obj or obj.project_id != pid:
            raise HTTPException(404, "业务对象不存在")
        return obj

    @app.get("/api/projects/{pid}/attachments")
    def attachments(pid: str, request: Request, db: DBSession = Depends(get_db)):
        u, _ = auth(request, db)
        authorized(db, u, pid)
        rows = db.scalars(select(EvidenceAttachment).where(EvidenceAttachment.project_id == pid).order_by(EvidenceAttachment.created_at.desc())).all()
        return [attachment_info(a) for a in rows]

    @app.post("/api/projects/{pid}/attachments/{target_type}/{target_id}", status_code=201)
    async def add_attachment(pid: str, target_type: str, target_id: str, request: Request,
                             upload: UploadFile = File(...), db: DBSession = Depends(get_db)):
        u, _ = auth(request, db, write=True)
        role = authorized(db, u, pid)
        if u.is_admin and mode == "production":
            raise HTTPException(403, "生产模式管理员不能上传业务证据")
        obj = attachment_target(db, pid, target_type, target_id)
        if target_type == "uat" and obj.status == "accepted":
            raise HTTPException(409, "已审核通过的UAT证据不可直接更改；重新执行测试将重置验收状态")
        if target_type == "uat" and not has_role(role, "tester", "admin"):
            raise HTTPException(403, "只有执行测试的角色能添加UAT证据")
        if target_type == "issue" and obj.status == "closed":
            raise HTTPException(409, "已关闭工单不允许继续追加证据，如需补测请创建新工单")
        if target_type == "issue":
            can_edit = has_role(role, "manager", "tester", "admin") or (has_role(role, "implementer") and obj.assignee_id == u.id)
            if not can_edit:
                raise HTTPException(403, "没有为此工单添加附件的权限")
        fname = (upload.filename or "").strip()
        if not fname or len(fname) > 140 or "/" in fname or "\\" in fname or ":" in fname or any(ord(c) < 32 for c in fname):
            raise HTTPException(422, "文件名称无效")
        ext = Path(fname).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".pdf"}:
            raise HTTPException(422, "仅支持PNG、JPEG、PDF文件")
        raw = await upload.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024 or not raw:
            raise HTTPException(413, "文件大小必须在1字节到5MB之间")
        if ext == ".png" and raw[:8] == b"\x89PNG\r\n\x1a\n":
            actual_type = "image/png"
        elif ext in {".jpg", ".jpeg"} and raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9"):
            actual_type = "image/jpeg"
        elif ext == ".pdf" and raw.startswith(b"%PDF-") and b"%%EOF" in raw[-1024:]:
            actual_type = "application/pdf"
        else:
            raise HTTPException(422, "文件内容与允许的扩展名不一致")
        aid = new_id()
        name = secrets.token_hex(20)
        diskpath = evidence_dir / name
        try:
            with diskpath.open("xb") as f:
                f.write(raw)
            a = EvidenceAttachment(id=aid, project_id=pid, target_type=target_type,
                                   target_id=target_id, uploaded_by=u.id, original_filename=fname,
                                   stored_name=name, media_type=actual_type, size_bytes=len(raw),
                                   digest_sha256=hashlib.sha256(raw).hexdigest())
            db.add(a)
            log(db, pid, u.id, "upload_evidence", target_type, target_id, {"file_id": aid, "sha256": a.digest_sha256})
            db.commit()
            return attachment_info(a)
        except Exception:
            db.rollback()
            diskpath.unlink(missing_ok=True)
            raise

    @app.get("/api/projects/{pid}/attachments/{aid}/file")
    def get_attachment(pid: str, aid: str, request: Request, preview: bool = False, db: DBSession = Depends(get_db)):
        u, _ = auth(request, db)
        authorized(db, u, pid)
        a = db.get(EvidenceAttachment, aid)
        if not a or a.project_id != pid: raise HTTPException(404, "附件不存在")
        file_path = evidence_dir / a.stored_name
        if not file_path.is_file(): raise HTTPException(404, "附件文件丢失，请联系管理员")
        show_inline = preview and a.media_type in {"image/png", "image/jpeg"}
        return FileResponse(file_path, media_type=a.media_type,
                            filename=a.original_filename,
                            content_disposition_type="inline" if show_inline else "attachment",
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return app


app = create_app()

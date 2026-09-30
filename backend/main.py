"""Personal Work OS API with a workspace-scoped PostgreSQL schema."""
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import os
import json
import logging
import time
import threading
from contextvars import ContextVar
import jwt
from pwdlib import PasswordHash
from uuid import UUID, uuid4
from typing import Any, Generator
from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, create_engine, func, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./workos.db")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})

class Base(DeclarativeBase): pass
class Role(str, Enum):
    owner = "Owner"; admin = "Admin"; member = "Member"; viewer = "Viewer"

class User(Base):
    __tablename__="users"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); name:Mapped[str]=mapped_column(String(120)); email:Mapped[str]=mapped_column(String(255),unique=True,index=True); password_hash:Mapped[str|None]=mapped_column(String(255),nullable=True); is_active:Mapped[bool]=mapped_column(default=True); token_version:Mapped[int]=mapped_column(Integer,default=0,server_default="0"); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class Workspace(Base):
    __tablename__="workspaces"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); name:Mapped[str]=mapped_column(String(160)); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class WorkspaceMember(Base):
    __tablename__="workspace_members"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); user_id:Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); role:Mapped[str]=mapped_column(String(20),default=Role.member.value); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); __table_args__=(Index("ix_workspace_members_workspace_user","workspace_id","user_id",unique=True),)
class Project(Base):
    __tablename__="projects"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); name:Mapped[str]=mapped_column(String(120)); code:Mapped[str]=mapped_column(String(24)); client_name:Mapped[str|None]=mapped_column(String(160),nullable=True); description:Mapped[str|None]=mapped_column(Text,nullable=True); status:Mapped[str]=mapped_column(String(30),default="Active",index=True); color:Mapped[str]=mapped_column(String(20),default="#58745d"); start_date:Mapped[date|None]=mapped_column(Date,nullable=True); notes:Mapped[str|None]=mapped_column(Text,nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); archived_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); __table_args__=(Index("ix_projects_workspace_code","workspace_id","code",unique=True),)
class ProjectMember(Base):
    __tablename__="project_members"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); project_id:Mapped[UUID]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),index=True); user_id:Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Contact(Base):
    __tablename__="contacts"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); name:Mapped[str]=mapped_column(String(160),index=True); organization:Mapped[str|None]=mapped_column(String(160),nullable=True); role:Mapped[str|None]=mapped_column(String(120),nullable=True); email:Mapped[str|None]=mapped_column(String(255),nullable=True); phone:Mapped[str|None]=mapped_column(String(40),nullable=True); notes:Mapped[str|None]=mapped_column(Text,nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class WorkItem(Base):
    __tablename__="work_items"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); project_id:Mapped[UUID]=mapped_column(ForeignKey("projects.id",ondelete="RESTRICT"),index=True); work_item_number:Mapped[str]=mapped_column(String(32),unique=True,index=True); title:Mapped[str]=mapped_column(String(255),index=True); description:Mapped[str|None]=mapped_column(Text,nullable=True); type:Mapped[str]=mapped_column(String(30),index=True); priority:Mapped[str]=mapped_column(String(30),index=True); status:Mapped[str]=mapped_column(String(30),default="New",index=True); source:Mapped[str|None]=mapped_column(String(30),index=True,nullable=True); reported_by_contact_id:Mapped[UUID|None]=mapped_column(ForeignKey("contacts.id",ondelete="SET NULL"),nullable=True); created_by_user_id:Mapped[UUID|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True); assigned_to_user_id:Mapped[UUID|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True); reported_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); due_date:Mapped[date|None]=mapped_column(Date,nullable=True); started_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); completed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True); root_cause:Mapped[str|None]=mapped_column(Text,nullable=True); solution:Mapped[str|None]=mapped_column(Text,nullable=True); testing_notes:Mapped[str|None]=mapped_column(Text,nullable=True); current_blocker:Mapped[str|None]=mapped_column(Text,nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,index=True)
class Activity(Base):
    __tablename__="activities"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); work_item_id:Mapped[UUID]=mapped_column(ForeignKey("work_items.id",ondelete="CASCADE"),index=True); user_id:Mapped[UUID|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True); activity_type:Mapped[str]=mapped_column(String(40)); note:Mapped[str]=mapped_column(Text); old_value:Mapped[str|None]=mapped_column(Text,nullable=True); new_value:Mapped[str|None]=mapped_column(Text,nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,index=True)
class Communication(Base):
    __tablename__="communications"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); work_item_id:Mapped[UUID]=mapped_column(ForeignKey("work_items.id",ondelete="CASCADE"),index=True); user_id:Mapped[UUID|None]=mapped_column(ForeignKey("users.id",ondelete="SET NULL"),nullable=True); communication_type:Mapped[str]=mapped_column(String(30)); contact_id:Mapped[UUID|None]=mapped_column(ForeignKey("contacts.id",ondelete="SET NULL"),nullable=True); subject:Mapped[str|None]=mapped_column(String(255),nullable=True); content:Mapped[str]=mapped_column(Text); communication_date:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Tag(Base):
    __tablename__="tags"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); name:Mapped[str]=mapped_column(String(80)); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); __table_args__=(Index("ix_tags_workspace_name","workspace_id","name",unique=True),)
class WorkItemTag(Base):
    __tablename__="work_item_tags"; work_item_id:Mapped[UUID]=mapped_column(ForeignKey("work_items.id",ondelete="CASCADE"),primary_key=True); tag_id:Mapped[UUID]=mapped_column(ForeignKey("tags.id",ondelete="CASCADE"),primary_key=True)
class WorkItemWatcher(Base):
    __tablename__="work_item_watchers"; work_item_id:Mapped[UUID]=mapped_column(ForeignKey("work_items.id",ondelete="CASCADE"),primary_key=True); user_id:Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),primary_key=True)
class DailyJournal(Base):
    __tablename__="daily_journals"; id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4); workspace_id:Mapped[UUID]=mapped_column(ForeignKey("workspaces.id",ondelete="CASCADE"),index=True); user_id:Mapped[UUID]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True); date:Mapped[date]=mapped_column(Date,index=True); summary:Mapped[str]=mapped_column(Text,default=""); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow); __table_args__=(Index("ix_daily_journals_workspace_user_date","workspace_id","user_id","date",unique=True),)
class DailyJournalItem(Base):
    __tablename__="daily_journal_items"; journal_id:Mapped[UUID]=mapped_column(ForeignKey("daily_journals.id",ondelete="CASCADE"),primary_key=True); work_item_id:Mapped[UUID]=mapped_column(ForeignKey("work_items.id",ondelete="CASCADE"),primary_key=True)

class ProjectIn(BaseModel):
    model_config=ConfigDict(from_attributes=True); name:str=Field(min_length=1,max_length=120); code:str=Field(min_length=2,max_length=24); client_name:str|None=None; description:str|None=None; status:str="Active"; color:str="#58745d"; start_date:date|None=None; notes:str|None=None
class WorkIn(BaseModel):
    title:str=Field(min_length=1,max_length=255); project_id:UUID; type:str; priority:str; status:str="New"; source:str|None=None; description:str|None=None; reported_by_contact_id:UUID|None=None; assigned_to_user_id:UUID|None=None; due_date:date|None=None; root_cause:str|None=None; solution:str|None=None; testing_notes:str|None=None; current_blocker:str|None=None
class ActivityIn(BaseModel):
    activity_type:str="Comment"; note:str=Field(min_length=1); old_value:str|None=None; new_value:str|None=None
class CommunicationIn(BaseModel):
    communication_type:str; contact_id:UUID|None=None; subject:str|None=None; content:str=Field(min_length=1); communication_date:datetime|None=None
class ContactIn(BaseModel):
    name:str=Field(min_length=1,max_length=160); organization:str|None=None; role:str|None=None; email:str|None=None; phone:str|None=None; notes:str|None=None
class MessageImportIn(BaseModel):
    content:str=Field(min_length=10)
    channel:str="Email"
    project_id:UUID|None=None
    contact_id:UUID|None=None
    sender_name:str|None=None
    sender_email:str|None=None
    confirm:bool=False
class RegisterIn(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    email:str=Field(min_length=5,max_length=255)
    password:str=Field(min_length=12,max_length=128)
class LoginIn(BaseModel):
    email:str
    password:str

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
logger = logging.getLogger("workos.api")
app=FastAPI(title="Work OS API",version="1.0.0")
JWT_ALGORITHM="HS256"
_WEAK_SECRETS={"development-only-change-me","replace-with-a-long-random-secret"}
password_hash=PasswordHash.recommended()

def jwt_secret()->str:
    """Authentication always fails closed: no usable secret means no tokens are issued or accepted."""
    secret=os.getenv("JWT_SECRET","")
    if len(secret)<32 or secret in _WEAK_SECRETS:
        raise RuntimeError("JWT_SECRET must be a unique random value of at least 32 characters")
    return secret
def token_ttl_minutes()->int: return int(os.getenv("ACCESS_TOKEN_TTL_MINUTES","720"))
def registration_allowed()->bool: return os.getenv("ALLOW_REGISTRATION","false").lower()=="true"
def issue_token(user:"User",workspace_id:UUID)->str:
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":str(user.id),"workspace_id":str(workspace_id),"ver":user.token_version,"iat":now,"exp":now+timedelta(minutes=token_ttl_minutes())},jwt_secret(),algorithm=JWT_ALGORITHM)
request_identity:ContextVar[tuple[UUID,UUID]|None]=ContextVar("request_identity", default=None)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            logger.info(json.dumps({"event":"request","request_id":request_id,"method":request.method,"path":request.url.path,"status":response.status_code,"duration_ms":round((time.perf_counter()-started)*1000,2)}))
            return response
        except Exception:
            logger.exception(json.dumps({"event":"unhandled_exception","request_id":request_id,"method":request.method,"path":request.url.path}))
            return JSONResponse(status_code=500, content={"error":{"code":"internal_error","message":"An unexpected error occurred.","request_id":request_id}})

PUBLIC_PATHS={"/api/health","/api/auth/register","/api/auth/login"}
def _unauthorized(code:str,message:str): return JSONResponse(status_code=401, headers={"WWW-Authenticate":"Bearer"}, content={"error":{"code":code,"message":message}})
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path=request.url.path
        if request.method=="OPTIONS" or not path.startswith("/api") or path in PUBLIC_PATHS:
            return await call_next(request)
        header=request.headers.get("Authorization","")
        if not header.startswith("Bearer "):
            return _unauthorized("authentication_required","Authentication required")
        try:
            payload=jwt.decode(header[7:], jwt_secret(), algorithms=[JWT_ALGORITHM], options={"require":["exp","iat","sub"]})
            uid=UUID(payload["sub"]); wid=UUID(payload["workspace_id"]); ver=int(payload["ver"])
            with Session(engine) as db:
                member=db.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id==uid,WorkspaceMember.workspace_id==wid))
                user=db.get(User,uid)
                if not member or not user or not user.is_active or user.token_version!=ver: raise ValueError("invalid identity")
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            return _unauthorized("invalid_token","Invalid or expired authentication token")
        reset=request_identity.set((wid,uid))
        try:
            return await call_next(request)
        finally:
            request_identity.reset(reset)

_rate_lock = threading.Lock()
_rate_windows: dict[str, tuple[int, int]] = {}
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != 'OPTIONS' and request.url.path.startswith('/api') and request.url.path != '/api/health':
            client = request.client.host if request.client else 'unknown'
            bucket = f"{client}:{'auth' if request.url.path in ('/api/auth/login','/api/auth/register') else 'api'}"
            limit = 10 if bucket.endswith(':auth') else 120
            now = int(time.time() // 60)
            with _rate_lock:
                window, count = _rate_windows.get(bucket, (now, 0))
                if window != now: window, count = now, 0
                count += 1; _rate_windows[bucket] = (window, count)
            if count > limit:
                return JSONResponse(status_code=429, headers={'Retry-After':'60'}, content={'error': {'code':'rate_limited','message':'Too many requests. Please retry shortly.'}})
        return await call_next(request)

# Starlette runs the LAST added middleware FIRST. Resulting order, outermost to innermost:
# CORS -> request logging -> rate limit -> auth. CORS must be outermost so browser preflights are
# answered before auth runs, and so 401/429 responses still carry CORS headers the frontend can read.
app.add_middleware(AuthMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    return JSONResponse(status_code=exc.status_code, content={"error":{"code":"request_error","message":str(exc.detail),"request_id":request_id}})
@app.on_event("startup")
def startup():
    # Fail fast on misconfiguration. The schema is owned by Alembic (`alembic upgrade head`);
    # the API never creates tables or seeds accounts on its own.
    jwt_secret()
    if os.getenv("REQUIRE_AUTH","").lower()=="false":
        logger.warning(json.dumps({"event":"config_ignored","setting":"REQUIRE_AUTH=false","detail":"authentication is always required"}))
def get_db()->Generator[Session,None,None]:
    with Session(engine) as db: yield db
def context():
    identity=request_identity.get()
    if not identity: raise HTTPException(401,"Authentication required")
    return identity
def project_payload(p:Project,db:Session):
    active=db.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.project_id==p.id,WorkItem.status!="Completed")) or 0; completed=db.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.project_id==p.id,WorkItem.status=="Completed")) or 0
    return {"id":str(p.id),"workspace_id":str(p.workspace_id),"name":p.name,"code":p.code,"client_name":p.client_name,"description":p.description,"status":p.status,"color":p.color,"start_date":p.start_date,"notes":p.notes,"created_at":p.created_at,"updated_at":p.updated_at,"archived_at":p.archived_at,"active_work_items":active,"completed_work_items":completed}
def item_payload(i): return {c.name:getattr(i,c.name) for c in i.__table__.columns}
@app.get("/api/health")
def health(): return {"status":"ok"}
def auth_payload(user:User,workspace:Workspace):
    return {"access_token":issue_token(user,workspace.id),"token_type":"bearer","expires_in":token_ttl_minutes()*60,"user":{"id":str(user.id),"name":user.name,"email":user.email},"workspace":{"id":str(workspace.id),"name":workspace.name}}
@app.post("/api/auth/register",status_code=201)
def register(data:RegisterIn,db:Session=Depends(get_db)):
    if not registration_allowed(): raise HTTPException(403,"Registration is disabled on this instance")
    if db.scalar(select(User).where(User.email==data.email.lower())): raise HTTPException(409,"An account with this email already exists")
    user=User(name=data.name,email=data.email.lower(),password_hash=password_hash.hash(data.password)); db.add(user); db.flush()
    workspace=Workspace(name=f"{data.name}'s Work OS"); db.add(workspace); db.flush(); db.add(WorkspaceMember(workspace_id=workspace.id,user_id=user.id,role=Role.owner.value)); db.commit()
    return auth_payload(user,workspace)
@app.post("/api/auth/login")
def login(data:LoginIn,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==data.email.lower()))
    if not user or not user.is_active or not user.password_hash or not password_hash.verify(data.password,user.password_hash): raise HTTPException(401,"Invalid email or password")
    membership=db.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id==user.id).order_by(WorkspaceMember.created_at))
    if not membership: raise HTTPException(403,"No workspace membership found")
    return auth_payload(user,db.get(Workspace,membership.workspace_id))
@app.post("/api/auth/logout",status_code=204)
def logout(db:Session=Depends(get_db)):
    """Revokes every token issued to the current user (all devices)."""
    _,uid=context(); user=db.get(User,uid); user.token_version=(user.token_version or 0)+1; db.commit()
@app.get("/api/auth/me")
def me(db:Session=Depends(get_db)):
    wid,uid=context(); user=db.get(User,uid); workspace=db.get(Workspace,wid); return {"user":{"id":str(user.id),"name":user.name,"email":user.email},"workspace":{"id":str(workspace.id),"name":workspace.name}}
@app.get("/api/projects")
def list_projects(include_archived:bool=False,db:Session=Depends(get_db)):
    wid,_=context(); q=select(Project).where(Project.workspace_id==wid)
    if not include_archived:q=q.where(Project.status!="Archived")
    return [project_payload(p,db) for p in db.scalars(q.order_by(Project.updated_at.desc())).all()]
def get_project_or_404(pid:UUID,db:Session):
    p=db.scalar(select(Project).where(Project.id==pid,Project.workspace_id==context()[0]))
    if not p: raise HTTPException(404,"Project not found")
    return p
@app.post("/api/projects",status_code=201)
def create_project(data:ProjectIn,db:Session=Depends(get_db)):
    wid,_=context(); code=data.code.upper()
    if db.scalar(select(Project).where(Project.workspace_id==wid,Project.code==code)): raise HTTPException(409,"Project code already exists in this workspace")
    p=Project(workspace_id=wid,code=code,**data.model_dump(exclude={"code"})); db.add(p); db.commit(); db.refresh(p); return project_payload(p,db)
@app.get("/api/projects/{pid}")
def get_project(pid:UUID,db:Session=Depends(get_db)): return project_payload(get_project_or_404(pid,db),db)
@app.put("/api/projects/{pid}")
def update_project(pid:UUID,data:ProjectIn,db:Session=Depends(get_db)):
    p=get_project_or_404(pid,db); code=data.code.upper(); dup=db.scalar(select(Project).where(Project.workspace_id==p.workspace_id,Project.code==code,Project.id!=p.id))
    if dup: raise HTTPException(409,"Project code already exists in this workspace")
    for k,v in data.model_dump().items(): setattr(p,k,code if k=="code" else v)
    db.commit(); db.refresh(p); return project_payload(p,db)
@app.patch("/api/projects/{pid}/archive")
def archive_project(pid:UUID,db:Session=Depends(get_db)):
    p=get_project_or_404(pid,db); p.status="Archived"; p.archived_at=datetime.utcnow(); db.commit(); return project_payload(p,db)
@app.patch("/api/projects/{pid}/restore")
def restore_project(pid:UUID,db:Session=Depends(get_db)):
    p=get_project_or_404(pid,db); p.status="Active"; p.archived_at=None; db.commit(); return project_payload(p,db)
def next_work_number(db):
    year=datetime.utcnow().year; last=db.scalar(select(WorkItem.work_item_number).where(WorkItem.work_item_number.like(f"WRK-{year}-%")).order_by(WorkItem.work_item_number.desc())); return f"WRK-{year}-{(int(last.rsplit('-',1)[1])+1 if last else 1):05d}"
def get_item_or_404(iid:UUID,db):
    item=db.scalar(select(WorkItem).where(WorkItem.id==iid,WorkItem.workspace_id==context()[0]))
    if not item: raise HTTPException(404,"Work item not found")
    return item
@app.get("/api/work-items")
def list_work_items(status:str|None=None,project_id:UUID|None=None,priority:str|None=None,type:str|None=None,source:str|None=None,search:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),db:Session=Depends(get_db)):
    q=select(WorkItem).where(WorkItem.workspace_id==context()[0])
    for field,value in ((WorkItem.status,status),(WorkItem.project_id,project_id),(WorkItem.priority,priority),(WorkItem.type,type),(WorkItem.source,source)):
        if value:q=q.where(field==value)
    if search:
        term=f"%{search}%"; q=q.where(or_(WorkItem.title.ilike(term),WorkItem.description.ilike(term),WorkItem.root_cause.ilike(term),WorkItem.solution.ilike(term)))
    total=db.scalar(select(func.count()).select_from(q.subquery())) or 0; rows=db.scalars(q.order_by(WorkItem.updated_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return {"items":[item_payload(i) for i in rows],"page":page,"page_size":page_size,"total":total}
@app.post("/api/work-items",status_code=201)
def create_work_item(data:WorkIn,db:Session=Depends(get_db)):
    wid,uid=context(); project=get_project_or_404(data.project_id,db)
    if project.status=="Archived": raise HTTPException(422,"Cannot create work in an archived project")
    item=WorkItem(workspace_id=wid,created_by_user_id=uid,work_item_number=next_work_number(db),**data.model_dump()); db.add(item); db.flush(); db.add(Activity(workspace_id=wid,work_item_id=item.id,user_id=uid,activity_type="Created",note="Work item created.")); db.commit(); db.refresh(item); return item_payload(item)
@app.get("/api/work-items/{iid}")
def get_work_item(iid:UUID,db:Session=Depends(get_db)): return item_payload(get_item_or_404(iid,db))
@app.put("/api/work-items/{iid}")
def update_work_item(iid:UUID,data:WorkIn,db:Session=Depends(get_db)):
    item=get_item_or_404(iid,db); old=item.status; get_project_or_404(data.project_id,db)
    for k,v in data.model_dump().items(): setattr(item,k,v)
    if item.status=="Completed" and old!="Completed": item.completed_at=datetime.utcnow()
    if old!=item.status: db.add(Activity(workspace_id=item.workspace_id,work_item_id=item.id,user_id=context()[1],activity_type="Status changed",note=f"Status changed from {old} to {item.status}.",old_value=old,new_value=item.status))
    db.commit(); db.refresh(item); return item_payload(item)
@app.patch("/api/work-items/{iid}/status")
def change_status(iid:UUID,status:str,db:Session=Depends(get_db)):
    item=get_item_or_404(iid,db); old=item.status; item.status=status; item.completed_at=datetime.utcnow() if status=="Completed" else None; db.add(Activity(workspace_id=item.workspace_id,work_item_id=item.id,user_id=context()[1],activity_type="Status changed",note=f"Status changed from {old} to {status}.",old_value=old,new_value=status)); db.commit(); db.refresh(item); return item_payload(item)
@app.get("/api/projects/{pid}/work-items")
def project_work_items(pid:UUID,db:Session=Depends(get_db)): get_project_or_404(pid,db); return [item_payload(i) for i in db.scalars(select(WorkItem).where(WorkItem.project_id==pid).order_by(WorkItem.updated_at.desc())).all()]
@app.get("/api/projects/{pid}/activity")
def project_activity(pid:UUID,db:Session=Depends(get_db)): get_project_or_404(pid,db); return [{"id":str(a.id),"work_item_id":str(a.work_item_id),"activity_type":a.activity_type,"note":a.note,"created_at":a.created_at} for a in db.scalars(select(Activity).join(WorkItem).where(WorkItem.project_id==pid).order_by(Activity.created_at.desc())).all()]
@app.post("/api/work-items/{iid}/activities",status_code=201)
def add_activity(iid:UUID,data:ActivityIn,db:Session=Depends(get_db)):
    item=get_item_or_404(iid,db); a=Activity(workspace_id=item.workspace_id,work_item_id=item.id,user_id=context()[1],**data.model_dump()); db.add(a); db.commit(); db.refresh(a); return {"id":str(a.id),"work_item_id":str(a.work_item_id),"activity_type":a.activity_type,"note":a.note,"created_at":a.created_at}
@app.get("/api/work-items/{iid}/activities")
def get_activities(iid:UUID,db:Session=Depends(get_db)): get_item_or_404(iid,db); return [{"id":str(a.id),"work_item_id":str(a.work_item_id),"activity_type":a.activity_type,"note":a.note,"old_value":a.old_value,"new_value":a.new_value,"created_at":a.created_at} for a in db.scalars(select(Activity).where(Activity.work_item_id==iid).order_by(Activity.created_at.asc())).all()]
@app.post("/api/work-items/{iid}/communications",status_code=201)
def add_communication(iid:UUID,data:CommunicationIn,db:Session=Depends(get_db)):
    item=get_item_or_404(iid,db); values=data.model_dump(); communication_date=values.pop("communication_date") or datetime.utcnow(); c=Communication(workspace_id=item.workspace_id,work_item_id=item.id,user_id=context()[1],communication_date=communication_date,**values); db.add(c); db.commit(); db.refresh(c); return {"id":str(c.id),"work_item_id":str(c.work_item_id),"communication_type":c.communication_type,"contact_id":c.contact_id,"subject":c.subject,"content":c.content,"communication_date":c.communication_date,"created_at":c.created_at}
@app.get("/api/work-items/{iid}/communications")
def get_communications(iid:UUID,db:Session=Depends(get_db)): get_item_or_404(iid,db); return [{"id":str(c.id),"work_item_id":str(c.work_item_id),"communication_type":c.communication_type,"contact_id":c.contact_id,"subject":c.subject,"content":c.content,"communication_date":c.communication_date,"created_at":c.created_at} for c in db.scalars(select(Communication).where(Communication.work_item_id==iid).order_by(Communication.communication_date.asc())).all()]
@app.get("/api/contacts")
def list_contacts(db:Session=Depends(get_db)): return [item_payload(c) for c in db.scalars(select(Contact).where(Contact.workspace_id==context()[0]).order_by(Contact.name)).all()]
@app.post("/api/contacts",status_code=201)
def create_contact(data:ContactIn,db:Session=Depends(get_db)): c=Contact(workspace_id=context()[0],**data.model_dump()); db.add(c); db.commit(); db.refresh(c); return item_payload(c)
@app.get("/api/reports/monthly")
def monthly_report(db:Session=Depends(get_db)):
    rows=db.scalars(select(WorkItem).where(WorkItem.workspace_id==context()[0])).all(); statuses=["New","In Progress","Waiting","Blocked","Testing","Completed"]; return {"total_work_items":len(rows),"by_status":{s:sum(1 for i in rows if i.status==s) for s in statuses}}

def extract_message_draft(content:str, channel:str):
    lines=[line.strip() for line in content.splitlines() if line.strip()]
    subject=next((line.split(":",1)[1].strip() for line in lines if line.lower().startswith("subject:")), "")
    sender=next((line.split(":",1)[1].strip() for line in lines if line.lower().startswith(("from:","sender:"))), "")
    lower=content.lower(); tags=[]
    for tag in ["Razorpay","India","INR","GST","UAT","Billing","Payment","Phase 0","WhatsApp"]:
        if tag.lower() in lower: tags.append(tag)
    title="Payment/order issue reported by message";
    if "razorpay" in lower: title="Razorpay payment order creation failure"
    if "fails" in lower or "failure" in lower or "error" in lower: work_type="Bug"
    else: work_type="Task"
    return {"channel":channel,"subject":subject,"sender":sender,"suggested_title":title,"suggested_type":work_type,"suggested_priority":"High" if any(x in lower for x in ["failure","fails","blocked","urgent"]) else "Medium","suggested_tags":tags,"content":content,"needs_project":True}

@app.post("/api/message-imports/analyze")
def analyze_message(data:MessageImportIn):
    draft=extract_message_draft(data.content,data.channel)
    if data.sender_name: draft["sender_name"]=data.sender_name
    if data.sender_email: draft["sender_email"]=data.sender_email
    return draft

@app.post("/api/message-imports/commit",status_code=201)
def commit_message(data:MessageImportIn,db:Session=Depends(get_db)):
    if not data.confirm: raise HTTPException(422,"Confirmation is required before importing a message")
    if not data.project_id: raise HTTPException(422,"Select the project related to this message")
    project=get_project_or_404(data.project_id,db); wid,uid=context(); contact=None
    if data.contact_id: contact=db.scalar(select(Contact).where(Contact.id==data.contact_id,Contact.workspace_id==wid))
    elif data.sender_name:
        contact=db.scalar(select(Contact).where(Contact.workspace_id==wid,Contact.name.ilike(data.sender_name)))
        if not contact:
            contact=Contact(workspace_id=wid,name=data.sender_name,email=data.sender_email); db.add(contact); db.flush()
    draft=extract_message_draft(data.content,data.channel)
    item=WorkItem(workspace_id=wid,project_id=project.id,created_by_user_id=uid,work_item_number=next_work_number(db),title=draft["suggested_title"],description=data.content,type=draft["suggested_type"],priority=draft["suggested_priority"],status="New",source=data.channel,reported_by_contact_id=contact.id if contact else None)
    db.add(item); db.flush(); db.add(Activity(workspace_id=wid,work_item_id=item.id,user_id=uid,activity_type="Created",note="Work item created from imported message.")); db.add(Communication(workspace_id=wid,work_item_id=item.id,user_id=uid,contact_id=contact.id if contact else None,communication_type=data.channel,subject=draft["subject"] or None,content=data.content)); db.commit(); db.refresh(item)
    return {"work_item":item_payload(item),"contact_id":str(contact.id) if contact else None,"message":"Original message preserved as a communication."}

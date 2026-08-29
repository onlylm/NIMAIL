from __future__ import annotations

import hmac
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .apple_service import AppleService
from .batch_service import BatchCreateService
from .config import DATA_DIR, WEB_DIR, ensure_data_dir
from .database import Database
from .deployment import apply_server_domain, load_deployment
from .imap_worker import ImapService
from .lifecycle import BackgroundWorkers, LifecycleService
from .schemas import (
    AppleBatchCreateRequest, AppleConfigureRequest, AppleCreateRequest, BootstrapRequest,
    DeploymentConfigureRequest, ImapConfigureRequest, LoginRequest, MailboxCreateRequest,
    PolicyUpdateRequest,
)
from .security import generate_cdk, hash_password, hash_secret, new_session, verify_password
from .viewer_compat import compatibility_cards_html


class RateLimiter:
    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, limit: int, window: int) -> bool:
        now, cutoff = time.monotonic(), time.monotonic() - window
        with self.lock:
            hits = self.hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


def client_ip(request: Request):
    return request.client.host if request.client else "unknown"


def require_admin(request: Request, authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "请先登录管理软件")
    token = authorization.split(" ", 1)[1].strip()
    if not request.app.state.db.validate_session(hash_secret(token)):
        raise HTTPException(401, "登录已失效，请重新登录")
    admin = request.app.state.db.get_admin()
    return {"id": admin["id"], "username": admin["username"], "session_token": token}


def create_app(data_dir: Path | None = None, web_dir: Path | None = None, start_workers: bool = True):
    data_dir, web_dir = ensure_data_dir(Path(data_dir or DATA_DIR)), Path(web_dir or WEB_DIR)
    db = Database(data_dir / "nimail-server.db")
    db.init()
    bootstrap_path = data_dir / "bootstrap-token.txt"
    if not db.admin_exists() and not bootstrap_path.exists():
        bootstrap_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")

    apple, imap = AppleService(db), ImapService(db)
    lifecycle = LifecycleService(db, apple)
    batch = BatchCreateService(db, apple)
    workers, limiter = BackgroundWorkers(imap, lifecycle), RateLimiter()

    @asynccontextmanager
    async def lifespan(app):
        if start_workers:
            workers.start()
        yield
        if start_workers:
            workers.stop()

    app = FastAPI(title="NIMAIL Server", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.db, app.state.apple, app.state.imap = db, apple, imap
    app.state.lifecycle, app.state.batch, app.state.bootstrap_path = lifecycle, batch, bootstrap_path

    def viewer_base_url(request: Request) -> str:
        deployment = load_deployment(data_dir)
        if deployment["mode"] == "server":
            return deployment["viewer_base_url"]
        return str(request.base_url).rstrip("/")

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers.update({
            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        })
        if request.url.path.startswith(("/api/", "/c")):
            response.headers.update({"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache",
                                     "X-Robots-Tag": "noindex, nofollow, noarchive"})
        if request.url.path.startswith("/c"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
            )
        return response

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "version": __version__}

    @app.get("/api/bootstrap/status")
    def bootstrap_status():
        return {"required": not db.admin_exists(),
                "token_file": "bootstrap-token.txt" if not db.admin_exists() else None}

    @app.post("/api/bootstrap", status_code=201)
    def bootstrap(payload: BootstrapRequest, request: Request):
        if db.admin_exists():
            raise HTTPException(409, "管理员已经初始化")
        if not limiter.allow(f"bootstrap:{client_ip(request)}", 10, 600):
            raise HTTPException(429, "尝试次数过多")
        try:
            expected = bootstrap_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            raise HTTPException(409, "初始化密钥不存在")
        if not hmac.compare_digest(expected, payload.bootstrap_token.strip()):
            raise HTTPException(403, "初始化密钥不正确")
        db.create_admin(payload.username, hash_password(payload.password))
        bootstrap_path.unlink(missing_ok=True)
        return {"success": True}

    @app.post("/api/admin/login")
    def login(payload: LoginRequest, request: Request):
        if not limiter.allow(f"login:{client_ip(request)}", 8, 300):
            raise HTTPException(429, "登录失败次数过多")
        admin = db.get_admin(payload.username)
        if not admin or not verify_password(payload.password, admin["password_hash"]):
            raise HTTPException(401, "管理员账号或密码错误")
        token, token_hash, expires_at = new_session()
        db.create_session(token_hash, expires_at)
        return {"success": True, "token": token, "expires_at": expires_at,
                "admin": {"id": 1, "username": admin["username"]}}

    @app.post("/api/admin/logout")
    def logout(admin=Depends(require_admin)):
        db.delete_session(hash_secret(admin["session_token"]))
        return {"success": True}

    @app.get("/api/admin/status")
    def admin_status(admin=Depends(require_admin)):
        mailboxes = db.list_mailboxes(False)
        return {"version": __version__, "admin": {"id": 1, "username": admin["username"]},
                "mailbox_count": len(mailboxes),
                "message_count": sum(item["message_count"] for item in mailboxes),
                "imap": {"configured": imap.configured, "email": imap.email_address,
                         "last_sync": imap.last_sync, "last_error": imap.last_error},
                "apple": {"configured": apple.configured, "region": apple.region,
                          "last_error": apple.last_error},
                "deployment": load_deployment(data_dir), "lifecycle": lifecycle.last_result}

    @app.get("/api/admin/deployment")
    def deployment(admin=Depends(require_admin)):
        return load_deployment(data_dir)

    @app.put("/api/admin/deployment")
    def configure_deployment(payload: DeploymentConfigureRequest, admin=Depends(require_admin)):
        try:
            return {"success": True, **apply_server_domain(data_dir, payload.domain)}
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except OSError as exc:
            raise HTTPException(500, f"无法保存服务器域名：{exc}")

    @app.get("/api/admin/mailboxes")
    def mailboxes(admin=Depends(require_admin)):
        return {"items": db.list_mailboxes(True)}

    @app.post("/api/admin/mailboxes", status_code=201)
    def create_mailbox(payload: MailboxCreateRequest, request: Request, admin=Depends(require_admin)):
        cdk = payload.cdk or generate_cdk()
        try:
            item = db.create_mailbox(payload.address, payload.service_name, cdk,
                                     payload.deactivate_after_seconds, payload.message_retention_seconds,
                                     payload.cdk_retention_seconds, payload.apple_action)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "邮箱地址或 CDK 已存在")
        return {"item": item, "viewer_url": f"{viewer_base_url(request)}/c/{cdk}"}

    @app.delete("/api/admin/mailboxes/{mailbox_id}")
    def delete_mailbox(mailbox_id: str, apple_delete: bool = Query(False), admin=Depends(require_admin)):
        mailbox = db.get_mailbox(mailbox_id)
        if not mailbox:
            raise HTTPException(404, "邮箱不存在")
        if apple_delete:
            try:
                apple.apply_lifecycle(mailbox["address"], "delete")
            except Exception as exc:
                raise HTTPException(400, f"Apple 删除失败：{exc}")
        db.delete_mailbox(mailbox_id)
        return {"success": True, "apple_deleted": apple_delete}

    @app.post("/api/admin/mailboxes/{mailbox_id}/rotate-cdk")
    def rotate_cdk(mailbox_id: str, request: Request, admin=Depends(require_admin)):
        cdk = generate_cdk()
        if not db.rotate_cdk(mailbox_id, cdk):
            raise HTTPException(404, "邮箱不存在")
        return {"cdk": cdk, "viewer_url": f"{viewer_base_url(request)}/c/{cdk}"}

    @app.put("/api/admin/mailboxes/{mailbox_id}/policy")
    def policy(mailbox_id: str, payload: PolicyUpdateRequest, admin=Depends(require_admin)):
        if not db.update_policy(mailbox_id, payload.deactivate_after_seconds,
                                payload.message_retention_seconds, payload.cdk_retention_seconds,
                                payload.apple_action):
            raise HTTPException(404, "邮箱不存在")
        return {"item": db.get_mailbox(mailbox_id, True)}

    @app.get("/api/admin/mailboxes/{mailbox_id}/messages")
    def admin_messages(mailbox_id: str, limit: int = Query(50, ge=1, le=100), admin=Depends(require_admin)):
        mailbox = db.get_mailbox(mailbox_id)
        if not mailbox:
            raise HTTPException(404, "邮箱不存在")
        return {"mailbox": mailbox, "items": db.list_messages(mailbox_id, limit, True)}

    @app.post("/api/admin/imap/configure")
    def configure_imap(payload: ImapConfigureRequest, admin=Depends(require_admin)):
        try:
            imap.configure(payload.email, payload.app_password, True)
        except Exception as exc:
            raise HTTPException(400, f"iCloud IMAP 连接失败：{exc}")
        return {"success": True}

    @app.post("/api/admin/imap/sync")
    def sync_imap(admin=Depends(require_admin)):
        try:
            return {"success": True, **imap.sync()}
        except Exception as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/admin/apple/configure")
    def configure_apple(payload: AppleConfigureRequest, admin=Depends(require_admin)):
        try:
            count = apple.configure(payload.cookie.strip(), payload.region)
        except Exception as exc:
            apple.last_error = str(exc)
            raise HTTPException(400, f"Apple 会话验证失败：{exc}")
        return {"success": True, "alias_count": count}

    @app.post("/api/admin/apple/create", status_code=201)
    def create_apple(payload: AppleCreateRequest, request: Request, admin=Depends(require_admin)):
        try:
            address = apple.create_alias(payload.label, payload.note)
            cdk = payload.cdk or generate_cdk()
            item = db.create_mailbox(address, payload.label, cdk, payload.deactivate_after_seconds,
                                     payload.message_retention_seconds, payload.cdk_retention_seconds,
                                     payload.apple_action)
        except Exception as exc:
            raise HTTPException(400, str(exc))
        return {"item": item, "viewer_url": f"{viewer_base_url(request)}/c/{cdk}"}

    @app.post("/api/admin/apple/batch", status_code=202)
    def start_batch(payload: AppleBatchCreateRequest, admin=Depends(require_admin)):
        try:
            job = batch.start(payload)
        except Exception as exc:
            raise HTTPException(400, str(exc))
        return {"success": True, "job": job}

    def add_viewer_urls(job: dict | None, request: Request):
        if not job:
            return None
        base = viewer_base_url(request)
        for item in job["items"]:
            if item.get("cdk"):
                item["viewer_url"] = f"{base}/c/{item['cdk']}"
        return job

    @app.get("/api/admin/apple/batch/latest")
    def latest_batch(request: Request, admin=Depends(require_admin)):
        return {"job": add_viewer_urls(db.latest_batch_job(), request)}

    @app.get("/api/admin/apple/batch/{job_id}")
    def batch_status(job_id: str, request: Request, admin=Depends(require_admin)):
        job = db.get_batch_job(job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        return {"job": add_viewer_urls(job, request)}

    @app.post("/api/admin/lifecycle/run")
    def run_lifecycle(admin=Depends(require_admin)):
        return {"success": True, **lifecycle.run_once()}

    @app.get("/api/public/c/{cdk}")
    def public_inbox(cdk: str, request: Request, limit: int = Query(20, ge=1, le=50),
                     refresh: bool = Query(False)):
        if not limiter.allow(f"public:{client_ip(request)}", 120, 60):
            raise HTTPException(429, "访问过于频繁")
        mailbox = db.mailbox_by_cdk(cdk)
        if not mailbox:
            raise HTTPException(404, "CDK 不存在或已失效")
        # The explicit viewer button can request one immediate upstream check.
        # The global limiter prevents public clients from hammering iCloud IMAP.
        if refresh and imap.configured and limiter.allow("public-imap-refresh", 1, 3):
            try:
                imap.sync()
            except Exception:
                # Keep the mailbox readable when iCloud is temporarily slow.
                pass
            mailbox = db.mailbox_by_cdk(cdk) or mailbox
        return {"mailbox": {key: mailbox[key] for key in (
                    "address", "service_name", "state", "message_count", "first_message_at",
                    "deactivate_due_at", "purge_due_at", "cdk_expires_at")},
                "items": db.list_messages(mailbox["id"], limit, False)}

    @app.get("/api/public/c/{cdk}/messages/{message_id}")
    def public_message(cdk: str, message_id: int, request: Request):
        if not limiter.allow(f"detail:{client_ip(request)}", 180, 60):
            raise HTTPException(429, "访问过于频繁")
        mailbox = db.mailbox_by_cdk(cdk)
        if not mailbox:
            raise HTTPException(404, "CDK 不存在或已失效")
        item = db.get_message(mailbox["id"], message_id)
        if not item:
            raise HTTPException(404, "邮件不存在")
        return {"item": item}

    if web_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=web_dir), name="assets")

        @app.get("/c", include_in_schema=False)
        def viewer_root():
            return FileResponse(web_dir / "index.html")

        @app.get("/c/{cdk}", include_in_schema=False)
        def viewer_cdk(cdk: str):
            template = (web_dir / "index.html").read_text(encoding="utf-8")
            mailbox = db.mailbox_by_cdk(cdk)
            items = db.list_messages(mailbox["id"], 50, True) if mailbox else []
            compatibility = compatibility_cards_html(items, mailbox["address"] if mailbox else "")
            return HTMLResponse(template.replace("<!--NIMAIL_COMPAT_CARDS-->", compatibility))

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/c", 307)

    return app


app = create_app()

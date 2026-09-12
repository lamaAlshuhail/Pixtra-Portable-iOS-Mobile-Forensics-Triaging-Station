from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.services import auth as auth_svc
from app.services.database import get_db


router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class CreateUserIn(BaseModel):
    username: str
    full_name: str
    role: str
    password: str
    email: Optional[str] = None


class UpdateUserIn(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class ResetPasswordIn(BaseModel):
    new_password: str


def get_current_examiner(
    request: Request,
    x_pixtra_token: Optional[str] = Header(default=None, alias="X-Pixtra-Token"),
) -> dict:
    if not x_pixtra_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = get_db()
    sess = auth_svc.lookup_session(db, x_pixtra_token)
    if not sess:
        raise HTTPException(status_code=401, detail="Session expired")
    row = db.execute(
        "SELECT * FROM examiners WHERE id = ? LIMIT 1",
        (sess["examiner_id"],),
    ).fetchone()
    if not row:
        auth_svc.invalidate_session(db, x_pixtra_token)
        raise HTTPException(status_code=401, detail="Session invalid")
    if not row["is_active"]:
        auth_svc.invalidate_session(db, x_pixtra_token)
        raise HTTPException(status_code=401, detail="Account deactivated")

    auth_svc.touch_session(db, x_pixtra_token)

    examiner = dict(row)
    if examiner["must_change_password"]:
        path = request.url.path
        allowed_prefixes = (
            "/api/auth/change-password",
            "/api/auth/logout",
            "/api/auth/me",
        )
        if not any(path.startswith(p) for p in allowed_prefixes):
            raise HTTPException(
                status_code=403, detail="must_change_password",
            )
    return examiner


def require_role(*roles: str):
    def dep(examiner: dict = Depends(get_current_examiner)) -> dict:
        if examiner["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return examiner
    return dep


@router.post("/login")
async def login(body: LoginIn, request: Request):
    db = get_db()
    username = (body.username or "").strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="Username and password required")

    locked, mins = auth_svc.is_locked_out(db, username)
    if locked:
        raise HTTPException(
            status_code=429,
            detail=f"Account locked. Try again in {mins} minutes.",
        )

    row = db.execute(
        "SELECT * FROM examiners WHERE username = ? AND is_active = 1 LIMIT 1",
        (username,),
    ).fetchone()
    ip_addr = request.client.host if request.client else None

    if not row or not auth_svc.verify_password(body.password, row["password_hash"]):
        auth_svc.record_failed_attempt(db, username, ip_addr)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    auth_svc.clear_failed_attempts(db, username)
    sess = auth_svc.create_session(db, row["id"], ip_addr)
    db.execute(
        "UPDATE examiners SET last_login_at = ? WHERE id = ?",
        (sess["expires_at"], row["id"]),
    )
    db.commit()
    examiner_pub = auth_svc.public_examiner(dict(row))
    return {
        "token": sess["token"],
        "expires_at": sess["expires_at"],
        "examiner": examiner_pub,
    }


@router.get("/me")
async def me(
    x_pixtra_token: Optional[str] = Header(default=None, alias="X-Pixtra-Token"),
):
    if not x_pixtra_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = get_db()
    sess = auth_svc.lookup_session(db, x_pixtra_token)
    if not sess:
        raise HTTPException(status_code=401, detail="Session expired")
    row = db.execute(
        "SELECT * FROM examiners WHERE id = ? LIMIT 1",
        (sess["examiner_id"],),
    ).fetchone()
    if not row:
        auth_svc.invalidate_session(db, x_pixtra_token)
        raise HTTPException(status_code=401, detail="Session invalid")
    auth_svc.touch_session(db, x_pixtra_token)
    return {"examiner": auth_svc.public_examiner(dict(row))}


@router.post("/logout")
async def logout(
    x_pixtra_token: Optional[str] = Header(default=None, alias="X-Pixtra-Token"),
):
    if x_pixtra_token:
        auth_svc.invalidate_session(get_db(), x_pixtra_token)
    return {"success": True}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordIn,
    examiner: dict = Depends(get_current_examiner),
):
    if not body.new_password or len(body.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="New password must be at least 8 characters",
        )
    if body.new_password == body.old_password:
        raise HTTPException(
            status_code=400, detail="New password must differ from current",
        )
    if not auth_svc.verify_password(body.old_password, examiner["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password incorrect")

    db = get_db()
    db.execute(
        """
        UPDATE examiners
           SET password_hash = ?, must_change_password = 0,
               password_changed_at = ?
         WHERE id = ?
        """,
        (
            auth_svc.hash_password(body.new_password),
            auth_svc._now_iso(),
            examiner["id"],
        ),
    )
    db.commit()
    return {"success": True}


_VALID_ROLES = {"examiner", "supervisor", "viewer"}


@router.get("/users")
async def list_users(_: dict = Depends(require_role("supervisor"))):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM examiners ORDER BY created_at ASC"
    ).fetchall()
    return {"users": [auth_svc.public_examiner(dict(r)) for r in rows]}


@router.post("/users")
async def create_user(
    body: CreateUserIn,
    actor: dict = Depends(require_role("supervisor")),
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if not body.username.strip():
        raise HTTPException(status_code=400, detail="Username required")
    if len(body.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters",
        )
    db = get_db()
    existing = db.execute(
        "SELECT id FROM examiners WHERE username = ?", (body.username,),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    db.execute(
        """
        INSERT INTO examiners (
            username, full_name, email, role, password_hash,
            must_change_password, is_active, created_at, created_by
        ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
        """,
        (
            body.username, body.full_name, body.email, body.role,
            auth_svc.hash_password(body.password),
            auth_svc._now_iso(), actor["id"],
        ),
    )
    db.commit()
    new_id = db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    new_row = db.execute(
        "SELECT * FROM examiners WHERE id = ?", (new_id,),
    ).fetchone()
    return {"user": auth_svc.public_examiner(dict(new_row))}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserIn,
    actor: dict = Depends(require_role("supervisor")),
):
    db = get_db()
    row = db.execute(
        "SELECT * FROM examiners WHERE id = ?", (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    fields: list[str] = []
    params: list = []
    if body.full_name is not None:
        fields.append("full_name = ?")
        params.append(body.full_name)
    if body.email is not None:
        fields.append("email = ?")
        params.append(body.email)
    if body.role is not None:
        if body.role not in _VALID_ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        if user_id == actor["id"] and body.role != actor["role"]:
            raise HTTPException(
                status_code=400,
                detail="Cannot modify own role",
            )
        fields.append("role = ?")
        params.append(body.role)
    if body.is_active is not None:
        if user_id == actor["id"] and not body.is_active:
            raise HTTPException(
                status_code=400, detail="Cannot deactivate self",
            )
        fields.append("is_active = ?")
        params.append(1 if body.is_active else 0)

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(user_id)
    db.execute(
        f"UPDATE examiners SET {', '.join(fields)} WHERE id = ?", params,
    )
    db.commit()
    updated = db.execute(
        "SELECT * FROM examiners WHERE id = ?", (user_id,),
    ).fetchone()
    return {"user": auth_svc.public_examiner(dict(updated))}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    body: ResetPasswordIn,
    actor: dict = Depends(require_role("supervisor")),
):
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters",
        )
    db = get_db()
    row = db.execute(
        "SELECT id FROM examiners WHERE id = ?", (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    db.execute(
        """
        UPDATE examiners
           SET password_hash = ?, must_change_password = 1
         WHERE id = ?
        """,
        (auth_svc.hash_password(body.new_password), user_id),
    )
    db.execute("DELETE FROM sessions WHERE examiner_id = ?", (user_id,))
    db.commit()
    return {"success": True}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    actor: dict = Depends(require_role("supervisor")),
):
    if user_id == actor["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete self")
    db = get_db()
    row = db.execute(
        "SELECT id FROM examiners WHERE id = ?", (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    db.execute(
        "UPDATE examiners SET is_active = 0 WHERE id = ?", (user_id,),
    )
    db.execute("DELETE FROM sessions WHERE examiner_id = ?", (user_id,))
    db.commit()
    return {"success": True}

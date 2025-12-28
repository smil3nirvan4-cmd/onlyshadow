"""
S.S.I. SHADOW - User Service
============================
Service for managing users within organizations.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import secrets

from passlib.context import CryptContext
from jose import jwt, JWTError

from auth.models.entities import (
    User,
    UserCreate,
    UserUpdate,
    UserRole,
    Invitation,
    InvitationCreate,
    InvitationStatus,
    Session,
    AuditLog,
    AuditAction,
    has_permission,
    Permission,
)
from auth.services.organization_service import get_org_service

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    """
    Service for managing users.
    """
    
    def __init__(
        self,
        secret_key: str = None,
        access_token_expire_minutes: int = 60,
        refresh_token_expire_days: int = 7
    ):
        self.secret_key = secret_key or os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
        self.access_token_expire = access_token_expire_minutes
        self.refresh_token_expire = refresh_token_expire_days
        
        # In-memory stores (replace with database in production)
        self.users: Dict[str, User] = {}
        self.users_by_email: Dict[str, str] = {}  # email -> user_id
        self.invitations: Dict[str, Invitation] = {}
        self.invitations_by_token: Dict[str, str] = {}  # token -> invitation_id
        self.sessions: Dict[str, Session] = {}
        self.audit_logs: List[AuditLog] = []
    
    # =========================================================================
    # PASSWORD HASHING (using bcrypt directly for compatibility)
    # =========================================================================
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        import bcrypt
        pwd_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against hash."""
        import bcrypt
        pwd_bytes = plain_password.encode('utf-8')[:72]
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    
    # =========================================================================
    # USER CRUD
    # =========================================================================
    
    async def create_user(
        self,
        org_id: str,
        data: UserCreate,
        created_by: str = None
    ) -> User:
        """Create a new user."""
        # Check if email already exists
        if data.email.lower() in self.users_by_email:
            raise ValueError(f"User with email '{data.email}' already exists")
        
        # Check organization limit
        org_service = get_org_service()
        if not await org_service.check_limit(org_id, "users"):
            raise ValueError("Organization user limit reached")
        
        # Create user
        user = User(
            email=data.email.lower(),
            name=data.name,
            password_hash=self.hash_password(data.password) if data.password else None,
            organization_id=org_id,
            role=data.role
        )
        
        self.users[user.id] = user
        self.users_by_email[user.email] = user.id
        
        # Audit log
        await self._audit_log(
            org_id,
            created_by or "system",
            AuditAction.USER_CREATED,
            "user",
            user.id,
            f"User '{user.email}' created with role {user.role}"
        )
        
        logger.info(f"User created: {user.id} ({user.email})")
        return user
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self.users.get(user_id)
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        user_id = self.users_by_email.get(email.lower())
        if user_id:
            return self.users.get(user_id)
        return None
    
    async def get_users_by_organization(
        self,
        org_id: str,
        include_inactive: bool = False
    ) -> List[User]:
        """Get all users in an organization."""
        users = [
            user for user in self.users.values()
            if user.organization_id == org_id
            and (include_inactive or user.is_active)
        ]
        return sorted(users, key=lambda x: x.created_at, reverse=True)
    
    async def update_user(
        self,
        user_id: str,
        data: UserUpdate,
        updated_by: str
    ) -> Optional[User]:
        """Update a user."""
        user = self.users.get(user_id)
        if not user:
            return None
        
        changes = {}
        
        if data.name is not None and data.name != user.name:
            changes["name"] = {"old": user.name, "new": data.name}
            user.name = data.name
        
        if data.role is not None and data.role != user.role:
            changes["role"] = {"old": user.role, "new": data.role}
            user.role = data.role
            
            # Special audit for role changes
            await self._audit_log(
                user.organization_id,
                updated_by,
                AuditAction.USER_ROLE_CHANGED,
                "user",
                user_id,
                f"User role changed from {changes['role']['old']} to {changes['role']['new']}"
            )
        
        if data.avatar_url is not None:
            user.avatar_url = data.avatar_url
        
        if data.timezone is not None:
            user.timezone = data.timezone
        
        if data.locale is not None:
            user.locale = data.locale
        
        if data.preferences is not None:
            user.preferences.update(data.preferences)
        
        user.updated_at = datetime.utcnow()
        
        # Audit log
        if changes:
            await self._audit_log(
                user.organization_id,
                updated_by,
                AuditAction.USER_UPDATED,
                "user",
                user_id,
                "User updated",
                changes
            )
        
        return user
    
    async def delete_user(
        self,
        user_id: str,
        deleted_by: str
    ) -> bool:
        """Delete a user (soft delete)."""
        user = self.users.get(user_id)
        if not user:
            return False
        
        # Can't delete yourself
        if user_id == deleted_by:
            raise ValueError("Cannot delete yourself")
        
        # Can't delete the last owner
        if user.role == UserRole.OWNER:
            owners = [
                u for u in self.users.values()
                if u.organization_id == user.organization_id
                and u.role == UserRole.OWNER
                and u.is_active
            ]
            if len(owners) <= 1:
                raise ValueError("Cannot delete the last owner")
        
        user.is_active = False
        user.updated_at = datetime.utcnow()
        
        # Remove from email index
        if user.email in self.users_by_email:
            del self.users_by_email[user.email]
        
        # Audit log
        await self._audit_log(
            user.organization_id,
            deleted_by,
            AuditAction.USER_DELETED,
            "user",
            user_id,
            f"User '{user.email}' deleted"
        )
        
        logger.info(f"User deleted: {user_id}")
        return True
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    async def authenticate(
        self,
        email: str,
        password: str
    ) -> Optional[User]:
        """Authenticate a user with email and password."""
        user = await self.get_user_by_email(email)
        
        if not user:
            logger.debug(f"User not found: {email}")
            return None
        
        if not user.is_active:
            logger.debug(f"User not active: {email}")
            return None
        
        if not user.password_hash:
            logger.debug(f"User has no password (SSO): {email}")
            return None
        
        if not self.verify_password(password, user.password_hash):
            logger.debug(f"Invalid password for: {email}")
            return None
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        
        return user
    
    def create_access_token(self, user: User) -> Tuple[str, datetime]:
        """Create an access token."""
        expires = datetime.utcnow() + timedelta(minutes=self.access_token_expire)
        
        payload = {
            "sub": user.id,
            "org": user.organization_id,
            "role": user.role.value if isinstance(user.role, UserRole) else user.role,
            "exp": expires,
            "iat": datetime.utcnow(),
            "type": "access",
            "jti": secrets.token_urlsafe(16)
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return token, expires
    
    def create_refresh_token(self, user: User) -> Tuple[str, datetime]:
        """Create a refresh token."""
        expires = datetime.utcnow() + timedelta(days=self.refresh_token_expire)
        
        payload = {
            "sub": user.id,
            "org": user.organization_id,
            "exp": expires,
            "iat": datetime.utcnow(),
            "type": "refresh",
            "jti": secrets.token_urlsafe(16)
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return token, expires
    
    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict]:
        """Verify a JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            
            if payload.get("type") != token_type:
                return None
            
            return payload
        except JWTError:
            return None
    
    async def login(
        self,
        email: str,
        password: str,
        ip_address: str = None,
        user_agent: str = None
    ) -> Optional[Dict]:
        """Login a user."""
        user = await self.authenticate(email, password)
        
        if not user:
            return None
        
        # Create tokens
        access_token, access_expires = self.create_access_token(user)
        refresh_token, refresh_expires = self.create_refresh_token(user)
        
        # Create session
        session = Session(
            user_id=user.id,
            organization_id=user.organization_id,
            refresh_token_hash=self.hash_password(refresh_token),
            ip_address=ip_address or "unknown",
            expires_at=refresh_expires
        )
        self.sessions[session.id] = session
        
        # Audit log
        await self._audit_log(
            user.organization_id,
            user.id,
            AuditAction.USER_LOGIN,
            "session",
            session.id,
            f"User logged in from {ip_address}",
            metadata={"ip": ip_address, "user_agent": user_agent}
        )
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire * 60,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role.value if isinstance(user.role, UserRole) else user.role,
                "organization_id": user.organization_id,
                "permissions": [p.value for p in self.get_user_permissions(user)]
            }
        }
    
    async def refresh_tokens(self, refresh_token: str) -> Optional[Dict]:
        """Refresh tokens."""
        payload = self.verify_token(refresh_token, "refresh")
        
        if not payload:
            return None
        
        user = await self.get_user(payload["sub"])
        
        if not user or not user.is_active:
            return None
        
        # Create new tokens
        access_token, access_expires = self.create_access_token(user)
        new_refresh_token, refresh_expires = self.create_refresh_token(user)
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_expire * 60
        }
    
    async def logout(self, user_id: str, session_id: str = None):
        """Logout a user."""
        user = await self.get_user(user_id)
        
        if session_id:
            # Revoke specific session
            session = self.sessions.get(session_id)
            if session and session.user_id == user_id:
                session.is_active = False
                session.revoked_at = datetime.utcnow()
        else:
            # Revoke all sessions
            for session in self.sessions.values():
                if session.user_id == user_id:
                    session.is_active = False
                    session.revoked_at = datetime.utcnow()
        
        if user:
            await self._audit_log(
                user.organization_id,
                user_id,
                AuditAction.USER_LOGOUT,
                "session",
                session_id,
                "User logged out"
            )
    
    # =========================================================================
    # PERMISSIONS
    # =========================================================================
    
    def get_user_permissions(self, user: User) -> List[Permission]:
        """Get all permissions for a user based on their role."""
        from auth.models.entities import get_permissions
        return get_permissions(user.role)
    
    def check_permission(self, user: User, permission: Permission) -> bool:
        """Check if a user has a specific permission."""
        return has_permission(user.role, permission)
    
    # =========================================================================
    # INVITATIONS
    # =========================================================================
    
    async def create_invitation(
        self,
        org_id: str,
        data: InvitationCreate,
        invited_by: str
    ) -> Invitation:
        """Create an invitation to join an organization."""
        # Check if user already exists in org
        existing = await self.get_user_by_email(data.email)
        if existing and existing.organization_id == org_id:
            raise ValueError(f"User '{data.email}' is already a member")
        
        # Check for existing pending invitation
        for inv in self.invitations.values():
            if (inv.organization_id == org_id 
                and inv.email == data.email.lower()
                and inv.status == InvitationStatus.PENDING):
                raise ValueError(f"Pending invitation already exists for '{data.email}'")
        
        # Create invitation
        invitation = Invitation(
            organization_id=org_id,
            email=data.email.lower(),
            role=data.role,
            team_ids=data.team_ids,
            expires_at=datetime.utcnow() + timedelta(days=7),
            invited_by=invited_by
        )
        
        self.invitations[invitation.id] = invitation
        self.invitations_by_token[invitation.token] = invitation.id
        
        # Audit log
        await self._audit_log(
            org_id,
            invited_by,
            AuditAction.INVITATION_SENT,
            "invitation",
            invitation.id,
            f"Invitation sent to '{data.email}' with role {data.role}"
        )
        
        logger.info(f"Invitation created: {invitation.id} for {data.email}")
        return invitation
    
    async def get_invitation_by_token(self, token: str) -> Optional[Invitation]:
        """Get an invitation by token."""
        inv_id = self.invitations_by_token.get(token)
        if inv_id:
            return self.invitations.get(inv_id)
        return None
    
    async def accept_invitation(
        self,
        token: str,
        name: str,
        password: str
    ) -> Optional[User]:
        """Accept an invitation and create user."""
        invitation = await self.get_invitation_by_token(token)
        
        if not invitation:
            raise ValueError("Invalid invitation token")
        
        if invitation.status != InvitationStatus.PENDING:
            raise ValueError(f"Invitation is {invitation.status}")
        
        if invitation.expires_at < datetime.utcnow():
            invitation.status = InvitationStatus.EXPIRED
            raise ValueError("Invitation has expired")
        
        # Create user
        user = await self.create_user(
            invitation.organization_id,
            UserCreate(
                email=invitation.email,
                name=name,
                password=password,
                role=invitation.role
            ),
            created_by=invitation.invited_by
        )
        
        # Add to teams
        user.team_ids = invitation.team_ids
        user.is_verified = True
        
        # Update invitation
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = datetime.utcnow()
        invitation.accepted_by_user_id = user.id
        
        # Audit log
        await self._audit_log(
            invitation.organization_id,
            user.id,
            AuditAction.INVITATION_ACCEPTED,
            "invitation",
            invitation.id,
            f"Invitation accepted by '{user.email}'"
        )
        
        return user
    
    async def revoke_invitation(
        self,
        invitation_id: str,
        revoked_by: str
    ) -> bool:
        """Revoke a pending invitation."""
        invitation = self.invitations.get(invitation_id)
        
        if not invitation:
            return False
        
        if invitation.status != InvitationStatus.PENDING:
            return False
        
        invitation.status = InvitationStatus.REVOKED
        
        # Audit log
        await self._audit_log(
            invitation.organization_id,
            revoked_by,
            AuditAction.INVITATION_REVOKED,
            "invitation",
            invitation_id,
            f"Invitation to '{invitation.email}' revoked"
        )
        
        return True
    
    async def get_pending_invitations(self, org_id: str) -> List[Invitation]:
        """Get all pending invitations for an organization."""
        return [
            inv for inv in self.invitations.values()
            if inv.organization_id == org_id
            and inv.status == InvitationStatus.PENDING
        ]
    
    # =========================================================================
    # PASSWORD MANAGEMENT
    # =========================================================================
    
    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ) -> bool:
        """Change a user's password."""
        user = await self.get_user(user_id)
        
        if not user or not user.password_hash:
            return False
        
        if not self.verify_password(current_password, user.password_hash):
            return False
        
        user.password_hash = self.hash_password(new_password)
        user.updated_at = datetime.utcnow()
        
        return True
    
    async def request_password_reset(self, email: str) -> Optional[str]:
        """Request a password reset token."""
        user = await self.get_user_by_email(email)
        
        if not user or not user.is_active:
            # Don't reveal if user exists
            return None
        
        # Create reset token
        token = secrets.token_urlsafe(32)
        
        # In production, store in Redis with expiry
        # For now, just return the token
        
        return token
    
    async def reset_password(self, token: str, new_password: str) -> bool:
        """Reset password using a token."""
        # In production, verify token from Redis
        # For now, this is a placeholder
        return False
    
    # =========================================================================
    # SESSIONS
    # =========================================================================
    
    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all active sessions for a user."""
        return [
            session for session in self.sessions.values()
            if session.user_id == user_id and session.is_active
        ]
    
    async def revoke_session(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """Revoke a specific session."""
        session = self.sessions.get(session_id)
        
        if not session or session.user_id != user_id:
            return False
        
        session.is_active = False
        session.revoked_at = datetime.utcnow()
        
        return True
    
    async def revoke_all_sessions(self, user_id: str, except_session_id: str = None):
        """Revoke all sessions for a user."""
        for session in self.sessions.values():
            if session.user_id == user_id and session.id != except_session_id:
                session.is_active = False
                session.revoked_at = datetime.utcnow()
    
    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================
    
    async def _audit_log(
        self,
        org_id: str,
        actor_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str],
        description: str,
        changes: Dict = None,
        metadata: Dict = None
    ):
        """Create an audit log entry."""
        log = AuditLog(
            organization_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=changes,
            metadata=metadata or {}
        )
        
        self.audit_logs.append(log)
        logger.debug(f"Audit: {action} by {actor_id}")


# =============================================================================
# SINGLETON
# =============================================================================

_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    """Get or create the user service."""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service


async def init_user_service(
    secret_key: str = None,
    access_token_expire: int = 60,
    refresh_token_expire: int = 7
) -> UserService:
    """Initialize the user service."""
    global _user_service
    _user_service = UserService(
        secret_key=secret_key,
        access_token_expire_minutes=access_token_expire,
        refresh_token_expire_days=refresh_token_expire
    )
    return _user_service

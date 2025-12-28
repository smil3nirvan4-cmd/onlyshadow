"""
S.S.I. SHADOW - Authentication Routes
=====================================
REST API endpoints for authentication.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, Request

from api.models.schemas import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    UserResponse,
    ChangePasswordRequest,
    ErrorResponse,
)
from api.services.auth_service import get_auth_service
from api.middleware.auth import (
    get_current_user,
    check_rate_limit,
    AuthenticatedUser,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# =============================================================================
# LOGIN
# =============================================================================

@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Login",
    description="Authenticate with email and password to receive JWT tokens."
)
async def login(
    request: LoginRequest,
    response: Response,
    _: None = Depends(check_rate_limit)
):
    """
    Authenticate a user and return access and refresh tokens.
    
    - **email**: User's email address
    - **password**: User's password (minimum 8 characters)
    
    Returns:
    - **access_token**: Short-lived token for API requests (1 hour)
    - **refresh_token**: Long-lived token for refreshing (7 days)
    - **user**: User profile information
    """
    auth_service = get_auth_service()
    result = await auth_service.login(request.email, request.password)
    
    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )
    
    # Set refresh token as HTTP-only cookie (optional security measure)
    response.set_cookie(
        key="refresh_token",
        value=result["refresh_token"],
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60  # 7 days
    )
    
    return LoginResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(**result["user"])
    )


# =============================================================================
# REFRESH TOKEN
# =============================================================================

@router.post(
    "/refresh",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or expired refresh token"},
    },
    summary="Refresh tokens",
    description="Get new access and refresh tokens using a valid refresh token."
)
async def refresh_tokens(
    request: RefreshTokenRequest = None,
    http_request: Request = None,
    response: Response = None
):
    """
    Refresh access and refresh tokens.
    
    The refresh token can be provided either:
    - In the request body as `refresh_token`
    - In the `refresh_token` cookie
    """
    # Get refresh token from body or cookie
    refresh_token = None
    
    if request and request.refresh_token:
        refresh_token = request.refresh_token
    elif http_request:
        refresh_token = http_request.cookies.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token required"
        )
    
    auth_service = get_auth_service()
    result = await auth_service.refresh_tokens(refresh_token)
    
    if not result:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token"
        )
    
    # Get user info
    from api.services.auth_service import TokenPayload
    payload = auth_service.decode_token(result["access_token"])
    user = await auth_service.get_user(payload.sub)
    
    # Update cookie
    if response:
        response.set_cookie(
            key="refresh_token",
            value=result["refresh_token"],
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60
        )
    
    return LoginResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type=result["token_type"],
        expires_in=result["expires_in"],
        user=UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            organization_id=user.organization_id,
            organization_name=user.organization_name,
            created_at=user.created_at,
            last_login=user.last_login
        )
    )


# =============================================================================
# LOGOUT
# =============================================================================

@router.post(
    "/logout",
    status_code=204,
    summary="Logout",
    description="Logout and invalidate tokens."
)
async def logout(
    response: Response,
    http_request: Request,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Logout the current user.
    
    This will:
    - Revoke the access token
    - Revoke the refresh token (if provided in cookie)
    - Clear the refresh token cookie
    """
    auth_service = get_auth_service()
    
    # Get tokens
    auth_header = http_request.headers.get("Authorization", "")
    access_token = auth_header.replace("Bearer ", "") if auth_header else None
    refresh_token = http_request.cookies.get("refresh_token")
    
    # Revoke tokens
    if access_token:
        await auth_service.logout(access_token, refresh_token)
    
    # Clear cookie
    response.delete_cookie("refresh_token")
    
    return Response(status_code=204)


# =============================================================================
# CURRENT USER
# =============================================================================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get the profile of the currently authenticated user."
)
async def get_me(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get the current user's profile."""
    auth_service = get_auth_service()
    user_data = await auth_service.get_user(user.user_id)
    
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=user_data.id,
        email=user_data.email,
        name=user_data.name,
        role=user_data.role,
        organization_id=user_data.organization_id,
        organization_name=user_data.organization_name,
        created_at=user_data.created_at,
        last_login=user_data.last_login
    )


# =============================================================================
# CHANGE PASSWORD
# =============================================================================

@router.post(
    "/change-password",
    status_code=204,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid current password"},
    },
    summary="Change password",
    description="Change the password for the currently authenticated user."
)
async def change_password(
    request: ChangePasswordRequest,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Change the current user's password.
    
    - **current_password**: The user's current password
    - **new_password**: The new password (minimum 8 characters)
    """
    auth_service = get_auth_service()
    
    success = await auth_service.update_password(
        user.user_id,
        request.current_password,
        request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Invalid current password"
        )
    
    return Response(status_code=204)


# =============================================================================
# VALIDATE TOKEN (for services)
# =============================================================================

@router.get(
    "/validate",
    summary="Validate token",
    description="Validate an access token and return token info."
)
async def validate_token(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Validate the current access token.
    
    Returns basic token information for service-to-service validation.
    """
    return {
        "valid": True,
        "user_id": user.user_id,
        "organization_id": user.organization_id,
        "role": user.role
    }

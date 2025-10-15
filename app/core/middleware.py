"""
Authentication and request middleware for Wand Orchestrator.

Provides API key authentication, request logging, and security middleware.
"""

import time
import uuid
from typing import Optional, Callable, Dict, Any
from fastapi import HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import get_config
from app.core.logging_utils import get_logger, log_request


class APIKeyAuth(HTTPBearer):
    """API Key authentication handler."""
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
        self.config = get_config()
        self.logger = get_logger("wand.auth")
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        """Authenticate request using API key."""
        
        # Skip authentication in development mode if no API key is set
        if self.config.is_development() and not self.config.security.api_key:
            return None
        
        # Check for API key in headers
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            # Fallback to Authorization header
            credentials = await super().__call__(request)
            if credentials:
                api_key = credentials.credentials
        
        # Validate API key
        if not api_key:
            self.logger.warning("Missing API key", path=request.url.path)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        if api_key != self.config.security.api_key:
            self.logger.warning("Invalid API key", path=request.url.path)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        self.logger.debug("API key authenticated", path=request.url.path)
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=api_key)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.config = get_config()
        self.logger = get_logger("wand.middleware")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Record start time
        start_time = time.time()
        
        # Log incoming request
        log_request(
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            query_params=str(request.query_params) if request.query_params else None,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            self.logger.error(
                f"Request failed: {str(e)}",
                request_id=request_id,
                method=request.method,
                path=str(request.url.path),
                duration_ms=duration_ms,
                error=str(e)
            )
            raise
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Log response
        self.logger.info(
            f"Request completed: {response.status_code}",
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.config = get_config()
        self.logger = get_logger("wand.ratelimit")
        self.requests: Dict[str, list] = {}  # client_ip -> list of timestamps
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting based on client IP."""
        
        if not self.config.security.rate_limit_per_minute:
            return await call_next(request)
        
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        
        # Clean old requests (older than 1 minute)
        if client_ip in self.requests:
            self.requests[client_ip] = [
                timestamp for timestamp in self.requests[client_ip]
                if current_time - timestamp < 60
            ]
        else:
            self.requests[client_ip] = []
        
        # Check rate limit
        request_count = len(self.requests[client_ip])
        if request_count >= self.config.security.rate_limit_per_minute:
            self.logger.warning(
                f"Rate limit exceeded for {client_ip}",
                client_ip=client_ip,
                request_count=request_count,
                limit=self.config.security.rate_limit_per_minute
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.config.security.rate_limit_per_minute} requests per minute."
            )
        
        # Record this request
        self.requests[client_ip].append(current_time)
        
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to responses."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.config = get_config()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }
        
        # Add HSTS header in production
        if self.config.is_production():
            security_headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response


def get_current_request_id(request: Request) -> Optional[str]:
    """Get the current request ID from the request state."""
    return getattr(request.state, 'request_id', None)


# Authentication dependency
auth_handler = APIKeyAuth()

async def get_authenticated_user(credentials: HTTPAuthorizationCredentials = None) -> Optional[Dict[str, Any]]:
    """Get authenticated user information (placeholder for future user management)."""
    if credentials:
        return {"authenticated": True, "api_key": credentials.credentials}
    return None


# Export main components
__all__ = [
    "APIKeyAuth",
    "RequestLoggingMiddleware", 
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "auth_handler",
    "get_authenticated_user",
    "get_current_request_id"
]
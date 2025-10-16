"""
Exception handling middleware for Wand Orchestrator.

Provides global exception handling with standardized error responses,
logging, and proper HTTP status codes.
"""

import json
import traceback
import time
from typing import Any, Dict, Optional, Union

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import (
    WandException,
    ErrorResponse,
    ValidationError,
    DatabaseError,
    create_validation_error_from_pydantic,
    create_http_exception_from_wand_exception
)
from app.core.logging_utils import get_logger
from app.core.middleware import get_current_request_id


class ExceptionHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for global exception handling."""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = get_logger("wand.exceptions")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Handle exceptions globally and return standardized error responses."""
        try:
            response = await call_next(request)
            return response
            
        except WandException as exc:
            return await self._handle_wand_exception(request, exc)
            
        except HTTPException as exc:
            return await self._handle_http_exception(request, exc)
            
        except RequestValidationError as exc:
            return await self._handle_validation_exception(request, exc)
            
        except PydanticValidationError as exc:
            return await self._handle_pydantic_validation_exception(request, exc)
            
        except Exception as exc:
            return await self._handle_generic_exception(request, exc)
    
    async def _handle_wand_exception(self, request: Request, exc: WandException) -> JSONResponse:
        """Handle WandException with proper logging and response."""
        request_id = get_current_request_id(request)
        
        # Log the exception
        self.logger.error(
            f"WandException: {exc.error_type}",
            request_id=request_id,
            error_type=exc.error_type,
            message=exc.message,
            status_code=exc.status_code,
            path=str(request.url.path),
            method=request.method,
            details=len(exc.details) if exc.details else 0
        )
        
        # Create response
        response = exc.to_response(request_id)
        
        return JSONResponse(
            status_code=exc.status_code,
            content=response.dict()
        )
    
    async def _handle_http_exception(self, request: Request, exc: HTTPException) -> JSONResponse:
        """Handle FastAPI HTTPException."""
        request_id = get_current_request_id(request)
        
        # Log the exception
        self.logger.warning(
            f"HTTPException: {exc.status_code}",
            request_id=request_id,
            status_code=exc.status_code,
            detail=str(exc.detail),
            path=str(request.url.path),
            method=request.method
        )
        
        # Create standardized response
        error_response = ErrorResponse(
            status_code=exc.status_code,
            error_type="HTTPError",
            message=str(exc.detail),
            request_id=request_id,
            timestamp=time.time()
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.dict()
        )
    
    async def _handle_validation_exception(self, request: Request, exc: RequestValidationError) -> JSONResponse:
        """Handle FastAPI validation errors."""
        request_id = get_current_request_id(request)
        
        # Convert to WandException
        wand_exc = create_validation_error_from_pydantic(exc)
        
        # Log the validation error
        self.logger.warning(
            f"Validation error: {len(exc.errors())} errors",
            request_id=request_id,
            error_count=len(exc.errors()),
            path=str(request.url.path),
            method=request.method
        )
        
        # Create response
        response = wand_exc.to_response(request_id)
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response.dict()
        )
    
    async def _handle_pydantic_validation_exception(self, request: Request, exc: PydanticValidationError) -> JSONResponse:
        """Handle Pydantic validation errors."""
        request_id = get_current_request_id(request)
        
        # Convert to WandException
        wand_exc = create_validation_error_from_pydantic(exc)
        
        # Log the validation error
        self.logger.warning(
            "Pydantic validation error",
            request_id=request_id,
            path=str(request.url.path),
            method=request.method
        )
        
        # Create response
        response = wand_exc.to_response(request_id)
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response.dict()
        )
    
    async def _handle_generic_exception(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        request_id = get_current_request_id(request)
        
        # Log the exception with full traceback
        self.logger.error(
            f"Unhandled exception: {type(exc).__name__}",
            request_id=request_id,
            exception_type=type(exc).__name__,
            message=str(exc),
            path=str(request.url.path),
            method=request.method,
            traceback=traceback.format_exc()
        )
        
        # Create generic error response
        error_response = ErrorResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type="InternalServerError",
            message="An unexpected error occurred",
            request_id=request_id,
            timestamp=time.time()
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.dict()
        )


# Exception handler functions for FastAPI exception_handler decorator
async def wand_exception_handler(request: Request, exc: WandException) -> JSONResponse:
    """Exception handler for WandException."""
    middleware = ExceptionHandlingMiddleware(None)
    return await middleware._handle_wand_exception(request, exc)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Exception handler for validation errors."""
    middleware = ExceptionHandlingMiddleware(None)
    return await middleware._handle_validation_exception(request, exc)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Exception handler for HTTP exceptions."""
    middleware = ExceptionHandlingMiddleware(None)
    return await middleware._handle_http_exception(request, exc)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Exception handler for generic exceptions."""
    middleware = ExceptionHandlingMiddleware(None)
    return await middleware._handle_generic_exception(request, exc)


# Utility functions for raising common exceptions
def raise_not_found(resource_type: str, resource_id: str) -> None:
    """Raise a standardized not found exception."""
    from app.core.exceptions import ResourceNotFoundError
    raise ResourceNotFoundError(resource_type, resource_id)


def raise_validation_error(message: str, field: Optional[str] = None, value: Any = None) -> None:
    """Raise a standardized validation exception."""
    raise ValidationError(message, field, value)


def raise_execution_error(message: str, node_id: Optional[str] = None, agent_type: Optional[str] = None) -> None:
    """Raise a standardized execution exception."""
    from app.core.exceptions import ExecutionError
    raise ExecutionError(message, node_id, agent_type)


def raise_database_error(message: str, operation: Optional[str] = None) -> None:
    """Raise a standardized database exception."""
    raise DatabaseError(message, operation)


def raise_authentication_error(message: str = "Authentication required") -> None:
    """Raise a standardized authentication exception."""
    from app.core.exceptions import AuthenticationError
    raise AuthenticationError(message)


def raise_rate_limit_error(message: str = "Rate limit exceeded", retry_after: Optional[int] = None) -> None:
    """Raise a standardized rate limit exception."""
    from app.core.exceptions import RateLimitError
    raise RateLimitError(message, retry_after)


# Context manager for converting exceptions
class convert_exceptions:
    """Context manager to convert standard exceptions to WandExceptions."""
    
    def __init__(self, operation: str = "operation"):
        self.operation = operation
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return False
            
        # Convert common exceptions to WandExceptions
        if issubclass(exc_type, (ConnectionError, TimeoutError)):
            raise DatabaseError(f"Database {self.operation} failed: {exc_val}")
        elif issubclass(exc_type, ValueError):
            raise ValidationError(f"Invalid value in {self.operation}: {exc_val}")
        elif issubclass(exc_type, KeyError):
            raise ResourceNotFoundError(f"Resource not found in {self.operation}: {exc_val}")
        elif issubclass(exc_type, PermissionError):
            from app.core.exceptions import AuthorizationError
            raise AuthorizationError(f"Permission denied for {self.operation}")
        
        # Let other exceptions pass through
        return False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self.__exit__(exc_type, exc_val, exc_tb)


# Export main components
__all__ = [
    "ExceptionHandlingMiddleware",
    "wand_exception_handler",
    "validation_exception_handler", 
    "http_exception_handler",
    "generic_exception_handler",
    "raise_not_found",
    "raise_validation_error",
    "raise_execution_error",
    "raise_database_error",
    "raise_authentication_error",
    "raise_rate_limit_error",
    "convert_exceptions"
]
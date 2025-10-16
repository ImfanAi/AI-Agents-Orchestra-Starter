"""
Custom exception classes for Wand Orchestrator.

Provides domain-specific exceptions with proper HTTP status codes,
error details, and structured error responses.
"""

from typing import Any, Dict, List, Optional, Union
from fastapi import HTTPException, status
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information."""
    
    type: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field name if field-specific error")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional error context")


class ErrorResponse(BaseModel):
    """Standardized error response format."""
    
    error: bool = Field(True, description="Always true for error responses")
    status_code: int = Field(..., description="HTTP status code")
    error_type: str = Field(..., description="Error category or type")
    message: str = Field(..., description="Main error message")
    details: Optional[List[ErrorDetail]] = Field(None, description="Detailed error information")
    request_id: Optional[str] = Field(None, description="Request correlation ID")
    timestamp: float = Field(..., description="Error timestamp")
    documentation_url: Optional[str] = Field(None, description="Link to relevant documentation")


# Base exception classes
class WandException(Exception):
    """Base exception for all Wand Orchestrator errors."""
    
    def __init__(
        self,
        message: str,
        error_type: str = "WandError",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[List[ErrorDetail]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.details = details or []
        self.context = context or {}
        super().__init__(message)
    
    def to_response(self, request_id: Optional[str] = None) -> ErrorResponse:
        """Convert exception to standardized error response."""
        import time
        
        return ErrorResponse(
            status_code=self.status_code,
            error_type=self.error_type,
            message=self.message,
            details=self.details,
            request_id=request_id,
            timestamp=time.time(),
            documentation_url=self._get_documentation_url()
        )
    
    def _get_documentation_url(self) -> Optional[str]:
        """Get documentation URL for this error type."""
        # Could be extended to provide specific documentation links
        return None


# Configuration and validation errors
class ConfigurationError(WandException):
    """Configuration-related errors."""
    
    def __init__(self, message: str, config_field: Optional[str] = None, **kwargs):
        details = []
        if config_field:
            details.append(ErrorDetail(
                type="invalid_configuration",
                message=message,
                field=config_field
            ))
        
        super().__init__(
            message=message,
            error_type="ConfigurationError",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            **kwargs
        )


class ValidationError(WandException):
    """Validation errors for requests and data."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Any = None, details: Optional[List[ErrorDetail]] = None, **kwargs):
        # Build details list if not provided
        if details is None:
            details = []
            if field:
                details.append(ErrorDetail(
                    type="validation_error",
                    message=message,
                    field=field,
                    context={"value": value} if value is not None else None
                ))
        
        super().__init__(
            message=message,
            error_type="ValidationError",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
            **kwargs
        )


# Authentication and authorization errors
class AuthenticationError(WandException):
    """Authentication-related errors."""
    
    def __init__(self, message: str = "Authentication required", **kwargs):
        super().__init__(
            message=message,
            error_type="AuthenticationError",
            status_code=status.HTTP_401_UNAUTHORIZED,
            **kwargs
        )


class AuthorizationError(WandException):
    """Authorization-related errors."""
    
    def __init__(self, message: str = "Insufficient permissions", **kwargs):
        super().__init__(
            message=message,
            error_type="AuthorizationError",
            status_code=status.HTTP_403_FORBIDDEN,
            **kwargs
        )


# Resource errors
class ResourceNotFoundError(WandException):
    """Resource not found errors."""
    
    def __init__(self, message: str, resource_type: Optional[str] = None, resource_id: Optional[str] = None, **kwargs):
        # Use provided message or build default message
        if not message and resource_type and resource_id:
            message = f"{resource_type} with ID '{resource_id}' not found"
        
        details = []
        if resource_type and resource_id:
            details.append(ErrorDetail(
                type="resource_not_found",
                message=message,
                context={"resource_type": resource_type, "resource_id": resource_id}
            ))
        
        super().__init__(
            message=message,
            error_type="ResourceNotFoundError",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
            **kwargs
        )
        
        # Store for convenience access
        self.resource_type = resource_type
        self.resource_id = resource_id


class ResourceConflictError(WandException):
    """Resource conflict errors."""
    
    def __init__(self, resource_type: str, message: str, **kwargs):
        super().__init__(
            message=message,
            error_type="ResourceConflictError",
            status_code=status.HTTP_409_CONFLICT,
            details=[ErrorDetail(
                type="resource_conflict",
                message=message,
                context={"resource_type": resource_type}
            )],
            **kwargs
        )


# Execution and runtime errors
class ExecutionError(WandException):
    """Execution-related errors."""
    
    def __init__(self, message: str, node_id: Optional[str] = None, agent_type: Optional[str] = None, **kwargs):
        details = []
        context = {}
        
        if node_id:
            context["node_id"] = node_id
        if agent_type:
            context["agent_type"] = agent_type
            
        if context:
            details.append(ErrorDetail(
                type="execution_error",
                message=message,
                context=context
            ))
        
        super().__init__(
            message=message,
            error_type="ExecutionError",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            **kwargs
        )


class TimeoutError(ExecutionError):
    """Timeout-related errors."""
    
    def __init__(self, operation: str, timeout_seconds: int, **kwargs):
        message = f"Operation '{operation}' timed out after {timeout_seconds} seconds"
        super().__init__(
            message=message,
            error_type="TimeoutError",
            context={"operation": operation, "timeout_seconds": timeout_seconds},
            **kwargs
        )


class ConcurrencyError(ExecutionError):
    """Concurrency-related errors."""
    
    def __init__(self, message: str, current_load: Optional[int] = None, max_capacity: Optional[int] = None, **kwargs):
        context = {}
        if current_load is not None:
            context["current_load"] = current_load
        if max_capacity is not None:
            context["max_capacity"] = max_capacity
            
        super().__init__(
            message=message,
            error_type="ConcurrencyError",
            context=context,
            **kwargs
        )


# Rate limiting and quota errors
class RateLimitError(WandException):
    """Rate limiting errors."""
    
    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None, **kwargs):
        details = [ErrorDetail(
            type="rate_limit_exceeded",
            message=message,
            context={"retry_after_seconds": retry_after} if retry_after else None
        )]
        
        super().__init__(
            message=message,
            error_type="RateLimitError",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details,
            **kwargs
        )


# Plugin and tool errors
class PluginError(WandException):
    """Plugin-related errors."""
    
    def __init__(self, plugin_name: str, message: str, **kwargs):
        details = [ErrorDetail(
            type="plugin_error",
            message=message,
            context={"plugin_name": plugin_name}
        )]
        
        super().__init__(
            message=f"Plugin '{plugin_name}': {message}",
            error_type="PluginError",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            **kwargs
        )


class ToolError(WandException):
    """Tool-related errors."""
    
    def __init__(self, tool_name: str, message: str, **kwargs):
        details = [ErrorDetail(
            type="tool_error",
            message=message,
            context={"tool_name": tool_name}
        )]
        
        super().__init__(
            message=f"Tool '{tool_name}': {message}",
            error_type="ToolError",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            **kwargs
        )


# Database and storage errors
class DatabaseError(WandException):
    """Database-related errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        details = []
        if operation:
            details.append(ErrorDetail(
                type="database_error",
                message=message,
                context={"operation": operation}
            ))
        
        super().__init__(
            message=message,
            error_type="DatabaseError",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            **kwargs
        )


# Utility functions for exception handling
def create_validation_error_from_pydantic(exc: Exception) -> ValidationError:
    """Create ValidationError from Pydantic validation exception."""
    details = []
    
    if hasattr(exc, 'errors'):
        for error in exc.errors():
            field = '.'.join(str(x) for x in error.get('loc', []))
            details.append(ErrorDetail(
                type=error.get('type', 'validation_error'),
                message=error.get('msg', 'Validation failed'),
                field=field or None,
                context=error.get('ctx')
            ))
    
    return ValidationError(
        message="Request validation failed",
        details=details
    )


def create_http_exception_from_wand_exception(exc: WandException, request_id: Optional[str] = None) -> HTTPException:
    """Convert WandException to FastAPI HTTPException."""
    response = exc.to_response(request_id)
    return HTTPException(
        status_code=exc.status_code,
        detail=response.dict()
    )


# Export main classes and functions
__all__ = [
    # Response models
    "ErrorDetail",
    "ErrorResponse",
    
    # Base exceptions
    "WandException",
    
    # Specific exceptions
    "ConfigurationError",
    "ValidationError",
    "AuthenticationError",
    "AuthorizationError",
    "ResourceNotFoundError",
    "ResourceConflictError",
    "ExecutionError",
    "TimeoutError",
    "ConcurrencyError",
    "RateLimitError",
    "PluginError",
    "ToolError",
    "DatabaseError",
    
    # Utility functions
    "create_validation_error_from_pydantic",
    "create_http_exception_from_wand_exception"
]
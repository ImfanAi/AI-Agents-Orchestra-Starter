"""
Logging utilities for Wand Orchestrator.

Provides centralized logging configuration based on the app config,
with support for structured logging, file rotation, and different formats.
"""

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import get_config


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from LoggerAdapter or custom fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Add any additional attributes that were passed to the log call
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                'filename', 'module', 'lineno', 'funcName', 'created', 
                'msecs', 'relativeCreated', 'thread', 'threadName', 
                'processName', 'process', 'getMessage', 'exc_info', 
                'exc_text', 'stack_info', 'extra_fields'
            } and not key.startswith('_'):
                log_data[key] = value
        
        return json.dumps(log_data, default=str)


class ContextFilter(logging.Filter):
    """Add contextual information to log records."""
    
    def __init__(self, context: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.context = context or {}
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context to log record."""
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


class WandLogger:
    """Enhanced logger with context and structured logging support."""
    
    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(name)
        self.context = context or {}
        
        # Add context filter if context is provided
        if self.context:
            self.logger.addFilter(ContextFilter(self.context))
    
    def debug(self, message: str, **kwargs):
        """Log debug message with optional extra fields."""
        self._log(logging.DEBUG, message, kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message with optional extra fields."""
        self._log(logging.INFO, message, kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with optional extra fields."""
        self._log(logging.WARNING, message, kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with optional extra fields."""
        self._log(logging.ERROR, message, kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message with optional extra fields."""
        self._log(logging.CRITICAL, message, kwargs)
    
    def _log(self, level: int, message: str, extra_fields: Dict[str, Any]):
        """Internal logging method with extra fields support."""
        if extra_fields:
            # Create a custom LogRecord with extra fields
            record = self.logger.makeRecord(
                self.logger.name, level, "(unknown file)", 0, message, (), None
            )
            record.extra_fields = extra_fields
            self.logger.handle(record)
        else:
            self.logger.log(level, message)


def setup_logging() -> None:
    """Setup logging configuration based on app config."""
    config = get_config()
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set log level
    log_level = getattr(logging, config.logging.level)
    root_logger.setLevel(log_level)
    
    # Choose formatter
    if config.logging.json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(config.logging.format)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (if configured)
    if config.logging.file_path:
        file_path = Path(config.logging.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=config.logging.max_file_size_mb * 1024 * 1024,
            backupCount=config.logging.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set third-party library log levels to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Create main application logger
    app_logger = logging.getLogger("wand")
    app_logger.info(
        f"Logging configured - Level: {config.logging.level}, "
        f"JSON: {config.logging.json_format}, "
        f"File: {config.logging.file_path or 'None'}"
    )


def get_logger(name: str, context: Optional[Dict[str, Any]] = None) -> WandLogger:
    """Get a logger instance with optional context."""
    return WandLogger(name, context)


def log_config_on_startup() -> None:
    """Log configuration details on application startup."""
    config = get_config()
    logger = get_logger("wand.startup")
    
    logger.info(
        f"Starting {config.app_name} v{config.app_version}",
        environment=config.environment,
        debug=config.debug,
        host=config.host,
        port=config.port
    )
    
    if config.debug:
        logger.info("Debug mode enabled - detailed logging active")
    
    # Log configuration warnings
    warnings = config.validate_config()
    if warnings:
        logger.warning(f"Configuration issues detected: {len(warnings)}")
        for warning in warnings:
            logger.warning(f"Config warning: {warning}")


# Convenience functions for common logging patterns
def log_request(request_id: str, method: str, path: str, **kwargs):
    """Log HTTP request with standardized format."""
    logger = get_logger("wand.http")
    logger.info(
        f"{method} {path}",
        request_id=request_id,
        method=method,
        path=path,
        **kwargs
    )


def log_agent_execution(run_id: str, node_id: str, agent_type: str, status: str, **kwargs):
    """Log agent execution with standardized format."""
    logger = get_logger("wand.execution")
    logger.info(
        f"Agent {status}: {agent_type}",
        run_id=run_id,
        node_id=node_id,
        agent_type=agent_type,
        status=status,
        **kwargs
    )


def log_performance(operation: str, duration_ms: float, **kwargs):
    """Log performance metrics with standardized format."""
    logger = get_logger("wand.performance")
    logger.info(
        f"Performance: {operation}",
        operation=operation,
        duration_ms=duration_ms,
        **kwargs
    )


# Export main functions
__all__ = [
    "WandLogger",
    "setup_logging",
    "get_logger",
    "log_config_on_startup",
    "log_request",
    "log_agent_execution", 
    "log_performance"
]
"""
Configuration management for Wand Orchestrator.

Provides environment-based configuration with validation,
defaults, and type safety using Pydantic Settings.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings
import logging


class DatabaseConfig(BaseModel):
    """Database configuration settings."""
    
    url: str = Field(default="sqlite:///./wand.db", description="Database URL")
    max_connections: int = Field(default=10, ge=1, le=100)
    connection_timeout: int = Field(default=30, ge=1, le=300)
    echo_sql: bool = Field(default=False, description="Log SQL queries")
    
    @field_validator('url')
    @classmethod
    def validate_db_url(cls, v):
        if not v:
            raise ValueError("Database URL cannot be empty")
        return v


class SecurityConfig(BaseModel):
    """Security and authentication configuration."""
    
    api_key: Optional[str] = Field(default=None, description="API key for authentication")
    jwt_secret: Optional[str] = Field(default=None, description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_hours: int = Field(default=24, ge=1, le=168)  # 1 hour to 1 week
    cors_origins: List[str] = Field(default=["*"], description="Allowed CORS origins")
    cors_allow_credentials: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=60, ge=1)
    
    @field_validator('cors_origins')
    @classmethod
    def validate_cors_origins(cls, v):
        if not v:
            return ["*"]
        return v


class ExecutionConfig(BaseModel):
    """Execution engine configuration."""
    
    default_timeout_sec: int = Field(default=30, ge=1, le=3600)
    max_retries: int = Field(default=3, ge=0, le=10)
    default_concurrency: int = Field(default=5, ge=1, le=100)
    max_concurrency: int = Field(default=50, ge=1, le=1000)
    retry_backoff_factor: float = Field(default=2.0, ge=1.0, le=10.0)
    retry_max_delay: float = Field(default=60.0, ge=1.0, le=300.0)
    
    @model_validator(mode='after')
    def validate_max_concurrency(self):
        if self.max_concurrency < self.default_concurrency:
            raise ValueError("max_concurrency must be >= default_concurrency")
        return self


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        description="Log format"
    )
    json_format: bool = Field(default=False, description="Use JSON logging format")
    file_path: Optional[str] = Field(default=None, description="Log file path")
    max_file_size_mb: int = Field(default=100, ge=1, le=1000)
    backup_count: int = Field(default=5, ge=1, le=50)
    
    @field_validator('level')
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()


class MonitoringConfig(BaseModel):
    """Monitoring and observability configuration."""
    
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=9090, ge=1024, le=65535)
    health_check_interval: int = Field(default=30, ge=5, le=300)
    sse_queue_size: int = Field(default=1000, ge=10, le=10000)
    enable_tracing: bool = Field(default=False)
    jaeger_endpoint: Optional[str] = Field(default=None)


class CacheConfig(BaseModel):
    """Caching configuration."""
    
    enable_cache: bool = Field(default=True)
    cache_type: str = Field(default="memory", description="Cache type: memory, redis")
    redis_url: Optional[str] = Field(default=None, description="Redis URL for caching")
    default_ttl_seconds: int = Field(default=3600, ge=60, le=86400)  # 1 min to 1 day
    max_cache_size_mb: int = Field(default=100, ge=10, le=1000)
    
    @field_validator('cache_type')
    @classmethod
    def validate_cache_type(cls, v):
        valid_types = ['memory', 'redis']
        if v not in valid_types:
            raise ValueError(f"Cache type must be one of: {valid_types}")
        return v
    
    @model_validator(mode='after')
    def validate_redis_url(self):
        if self.cache_type == 'redis' and not self.redis_url:
            raise ValueError("Redis URL is required when cache_type is 'redis'")
        return self


class PluginConfig(BaseModel):
    """Plugin system configuration."""
    
    enable_dynamic_loading: bool = Field(default=False)
    plugin_directories: List[str] = Field(default_factory=list)
    allowed_plugin_types: List[str] = Field(default=["agent", "tool"])
    plugin_timeout_sec: int = Field(default=60, ge=1, le=300)
    enable_hot_reload: bool = Field(default=False)


class WandConfig(BaseSettings):
    """Main configuration class for Wand Orchestrator."""
    
    # Application settings
    app_name: str = Field(default="Wand Orchestrator")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    environment: str = Field(default="development")
    
    # Server settings
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1024, le=65535)
    workers: int = Field(default=1, ge=1, le=10)
    
    # Component configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    plugins: PluginConfig = Field(default_factory=PluginConfig)
    
    # Additional settings
    custom_settings: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
        # Allow reading from nested environment variables
        # e.g., DATABASE__URL, SECURITY__API_KEY, etc.
    }
        
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v):
        valid_envs = ['development', 'testing', 'staging', 'production']
        if v not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v
    
    @model_validator(mode='after')
    def validate_workers(self):
        if self.environment == 'production' and self.workers < 2:
            logging.warning("Consider using more workers in production")
        return self
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    def get_log_level(self) -> int:
        """Get numeric log level."""
        return getattr(logging, self.logging.level)
    
    def get_database_url(self) -> str:
        """Get the database URL with proper formatting."""
        url = self.database.url
        if url.startswith("sqlite:///"):
            # Ensure absolute path for SQLite
            path = url[10:]  # Remove "sqlite:///"
            if not Path(path).is_absolute():
                path = Path.cwd() / path
            return f"sqlite:///{path}"
        return url
    
    def update_from_dict(self, updates: Dict[str, Any]) -> None:
        """Update configuration from dictionary."""
        for key, value in updates.items():
            if hasattr(self, key):
                if isinstance(getattr(self, key), BaseModel):
                    # Handle nested config updates
                    current = getattr(self, key)
                    if isinstance(value, dict):
                        for nested_key, nested_value in value.items():
                            if hasattr(current, nested_key):
                                setattr(current, nested_key, nested_value)
                else:
                    setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.dict()
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of warnings/issues."""
        warnings = []
        
        # Security validations
        if self.is_production():
            if not self.security.api_key:
                warnings.append("API key not set in production environment")
            if not self.security.jwt_secret:
                warnings.append("JWT secret not set in production environment")
            if "*" in self.security.cors_origins:
                warnings.append("CORS allows all origins in production")
            if self.debug:
                warnings.append("Debug mode enabled in production")
        
        # Database validations
        if self.database.url.startswith("sqlite://") and self.is_production():
            warnings.append("SQLite database in production environment")
        
        # Performance validations
        if self.execution.default_concurrency > self.execution.max_concurrency:
            warnings.append("Default concurrency exceeds maximum concurrency")
        
        return warnings


@lru_cache()
def get_config() -> WandConfig:
    """Get cached configuration instance."""
    return WandConfig()


def reload_config() -> WandConfig:
    """Reload configuration (clears cache)."""
    get_config.cache_clear()
    return get_config()


# Configuration validation on import
def validate_startup_config() -> None:
    """Validate configuration at startup and log warnings."""
    try:
        config = get_config()
        warnings = config.validate_config()
        
        if warnings:
            logger = logging.getLogger("wand.config")
            logger.warning(f"Configuration warnings found:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
    except Exception as e:
        logging.error(f"Failed to validate configuration: {e}")
        raise


# Export commonly used functions
__all__ = [
    "WandConfig",
    "DatabaseConfig", 
    "SecurityConfig",
    "ExecutionConfig",
    "LoggingConfig",
    "MonitoringConfig",
    "CacheConfig",
    "PluginConfig",
    "get_config",
    "reload_config",
    "validate_startup_config"
]
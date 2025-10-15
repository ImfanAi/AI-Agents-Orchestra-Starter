#!/usr/bin/env python3
"""
Example script demonstrating the configuration management system.

This script shows how to:
1. Load and validate configuration
2. Use different configuration environments
3. Access nested configuration settings
4. Handle configuration validation
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import get_config, reload_config, WandConfig
from app.core.logging_utils import setup_logging, get_logger


def demonstrate_configuration():
    """Demonstrate configuration features."""
    print("=" * 60)
    print("Wand Orchestrator Configuration Management Demo")
    print("=" * 60)
    
    # 1. Load current configuration
    print("\n1. Loading current configuration...")
    config = get_config()
    
    print(f"   App Name: {config.app_name}")
    print(f"   Version: {config.app_version}")
    print(f"   Environment: {config.environment}")
    print(f"   Debug Mode: {config.debug}")
    print(f"   Host:Port: {config.host}:{config.port}")
    
    # 2. Demonstrate nested configuration
    print("\n2. Nested configuration access...")
    print(f"   Database URL: {config.database.url}")
    print(f"   Log Level: {config.logging.level}")
    print(f"   Default Timeout: {config.execution.default_timeout_sec}s")
    print(f"   Max Concurrency: {config.execution.max_concurrency}")
    
    # 3. Demonstrate configuration validation
    print("\n3. Configuration validation...")
    warnings = config.validate_config()
    if warnings:
        print(f"   Found {len(warnings)} warnings:")
        for warning in warnings:
            print(f"     - {warning}")
    else:
        print("   No validation warnings found!")
    
    # 4. Demonstrate environment-specific behavior
    print("\n4. Environment-specific features...")
    print(f"   Is Production: {config.is_production()}")
    print(f"   Is Development: {config.is_development()}")
    
    if config.is_development():
        print("   Development features enabled:")
        print("     - Auto-reload")
        print("     - Detailed error messages")
        print("     - Relaxed authentication")
    
    # 5. Demonstrate configuration updates
    print("\n5. Configuration update example...")
    original_timeout = config.execution.default_timeout_sec
    
    # Update configuration programmatically
    config.update_from_dict({
        "execution": {
            "default_timeout_sec": 60
        }
    })
    
    print(f"   Original timeout: {original_timeout}s")
    print(f"   Updated timeout: {config.execution.default_timeout_sec}s")
    
    # 6. Demonstrate logging configuration
    print("\n6. Logging configuration...")
    setup_logging()
    logger = get_logger("demo")
    
    logger.info("Configuration demo logging test")
    logger.debug("This debug message visibility depends on log level")
    logger.warning("Configuration system is working!", 
                   demo_param="test_value", 
                   config_env=config.environment)
    
    # 7. Show configuration dictionary
    print("\n7. Configuration export (partial)...")
    config_dict = config.to_dict()
    
    # Show only non-sensitive configuration
    safe_config = {
        "app_name": config_dict.get("app_name"),
        "app_version": config_dict.get("app_version"),
        "environment": config_dict.get("environment"),
        "database": {
            "url": "***" if "sqlite" not in config_dict.get("database", {}).get("url", "") else config_dict.get("database", {}).get("url"),
            "max_connections": config_dict.get("database", {}).get("max_connections")
        },
        "execution": config_dict.get("execution"),
        "logging": {
            k: v for k, v in config_dict.get("logging", {}).items() 
            if k != "file_path"  # Hide file path for demo
        }
    }
    
    import json
    print(json.dumps(safe_config, indent=2))


def demonstrate_environment_switching():
    """Demonstrate switching between environments."""
    print("\n" + "=" * 60)
    print("Environment Switching Demo")
    print("=" * 60)
    
    # Save original environment
    original_env = os.environ.get("ENVIRONMENT", "development")
    
    environments = ["development", "testing", "production"]
    
    for env in environments:
        print(f"\n--- Testing {env.upper()} environment ---")
        
        # Set environment variable
        os.environ["ENVIRONMENT"] = env
        
        # Reload configuration to pick up changes
        reload_config()
        config = get_config()
        
        print(f"Environment: {config.environment}")
        print(f"Debug: {config.debug}")
        print(f"Workers: {config.workers}")
        
        # Show environment-specific warnings
        warnings = config.validate_config()
        if warnings:
            print("Warnings:")
            for warning in warnings[:3]:  # Show only first 3
                print(f"  - {warning}")
        else:
            print("No warnings")
    
    # Restore original environment
    os.environ["ENVIRONMENT"] = original_env
    reload_config()


def main():
    """Main demo function."""
    try:
        demonstrate_configuration()
        demonstrate_environment_switching()
        
        print("\n" + "=" * 60)
        print("Configuration Management Demo Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Edit .env file to customize your configuration")
        print("2. Run 'python dev.py validate' to check configuration")
        print("3. Run 'python dev.py server' to start the server")
        print("4. Visit http://localhost:8000/docs for API documentation")
        
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
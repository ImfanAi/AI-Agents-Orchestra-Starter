#!/usr/bin/env python3
"""
Development utility script for Wand Orchestrator.

Provides commands for development tasks like running the server,
validating configuration, and managing the environment.
"""

import argparse
import asyncio
import sys
import os
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import get_config, validate_startup_config, reload_config
from app.core.logging_utils import setup_logging, get_logger


async def validate_config():
    """Validate the current configuration."""
    try:
        validate_startup_config()
        config = get_config()
        warnings = config.validate_config()
        
        print(f"[OK] Configuration loaded successfully")
        print(f"Environment: {config.environment}")
        print(f"Debug mode: {config.debug}")
        print(f"Database: {config.get_database_url()}")
        
        if warnings:
            print(f"\n[WARNING] Configuration warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        else:
            print("[OK] No configuration warnings")
            
        return len(warnings) == 0
    except Exception as e:
        print(f"[ERROR] Configuration validation failed: {e}")
        return False


def run_server():
    """Run the development server."""
    import uvicorn
    
    config = get_config()
    
    print(f"[START] Starting {config.app_name} v{config.app_version}")
    print(f"Environment: {config.environment}")
    print(f"Server: http://{config.host}:{config.port}")
    print(f"Docs: http://{config.host}:{config.port}/docs")
    
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        workers=1 if config.debug else config.workers,
        log_level=config.logging.level.lower(),
        access_log=True
    )


def create_env_file():
    """Create a .env file from the example."""
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if not env_example.exists():
        print("[ERROR] .env.example file not found")
        return False
    
    if env_file.exists():
        response = input("[INPUT] .env file already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return False
    
    # Copy the example file
    with open(env_example, 'r') as src, open(env_file, 'w') as dst:
        dst.write(src.read())
    
    print(f"[OK] Created .env file from .env.example")
    print(f"[INFO] Please edit .env file to customize your configuration")
    return True


def show_config():
    """Display current configuration."""
    try:
        config = get_config()
        config_dict = config.to_dict()
        
        print("[CONFIG] Current Configuration:")
        print("=" * 50)
        
        # Application settings
        print(f"Application: {config.app_name} v{config.app_version}")
        print(f"Environment: {config.environment}")
        print(f"Debug: {config.debug}")
        print(f"Host: {config.host}:{config.port}")
        
        # Database
        print(f"\nDatabase: {config.get_database_url()}")
        
        # Security (hide sensitive values)
        print(f"\nSecurity:")
        print(f"  API Key: {'***' if config.security.api_key else 'Not set'}")
        print(f"  JWT Secret: {'***' if config.security.jwt_secret else 'Not set'}")
        print(f"  CORS Origins: {config.security.cors_origins}")
        
        # Execution
        print(f"\nExecution:")
        print(f"  Default Timeout: {config.execution.default_timeout_sec}s")
        print(f"  Max Retries: {config.execution.max_retries}")
        print(f"  Default Concurrency: {config.execution.default_concurrency}")
        
        # Logging
        print(f"\nLogging:")
        print(f"  Level: {config.logging.level}")
        print(f"  Format: {'JSON' if config.logging.json_format else 'Text'}")
        print(f"  File: {config.logging.file_path or 'Console only'}")
        
        # Validation warnings
        warnings = config.validate_config()
        if warnings:
            print(f"\n[WARNING] Warnings:")
            for warning in warnings:
                print(f"  - {warning}")
        
    except Exception as e:
        print(f"[ERROR] Failed to load configuration: {e}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Wand Orchestrator Development Utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Server command
    server_parser = subparsers.add_parser('server', help='Run the development server')
    
    # Validation command
    validate_parser = subparsers.add_parser('validate', help='Validate configuration')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Show current configuration')
    
    # Setup command
    setup_parser = subparsers.add_parser('setup', help='Setup development environment')
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    args = parser.parse_args()
    
    if args.command == 'server':
        run_server()
    elif args.command == 'validate':
        success = asyncio.run(validate_config())
        sys.exit(0 if success else 1)
    elif args.command == 'config':
        show_config()
    elif args.command == 'setup':
        create_env_file()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
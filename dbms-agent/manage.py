#!/usr/bin/env python
"""Management script for dbms-agent"""
import os

from app import create_app


def main():
    """Main entry point"""
    app = create_app()

    host = app.config.get("AGENT_HOST", "0.0.0.0")
    port = app.config.get("AGENT_PORT", 5001)
    debug = app.config.get("AGENT_DEBUG", False)

    print(f"Starting dbms-agent on {host}:{port}")
    print(f"API Key: {'configured' if app.config.get('AGENT_API_KEY') else 'not configured'}")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
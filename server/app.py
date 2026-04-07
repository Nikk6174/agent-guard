# Dummy wrapper for OpenEnv CLI validation compliance.
# OpenEnv strictly searches for server/app.py with a literal 'def main(' string check.
from agent_guard.server.app import app
from agent_guard.server.app import main as real_main

def main():
    real_main()

if __name__ == "__main__":
    main()

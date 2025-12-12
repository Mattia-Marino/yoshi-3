#!/bin/bash

# Script to start the gRPC server
# Usage: ./start_server.sh [--foreground]

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

cd "$(dirname "$0")"

# Activate virtual environment
if [ -d ".venv" ]; then
    if [ -z "$VIRTUAL_ENV" ]; then
        echo -e "${BLUE}Activating virtual environment...${NC}"
        source .venv/bin/activate
    fi
fi

# Check if server is already running
if pgrep -f "python app.py" > /dev/null; then
    echo -e "${BLUE}Server is already running. PID: $(pgrep -f 'python app.py')${NC}"
    echo "To stop: ./stop_server.sh"
    exit 0
fi

# Start server
if [ "$1" = "--foreground" ]; then
    echo -e "${GREEN}Starting gRPC server in foreground...${NC}"
    python app.py
else
    echo -e "${GREEN}Starting gRPC server in background...${NC}"
    nohup python app.py > server.log 2>&1 &
    sleep 1
    
    if pgrep -f "python app.py" > /dev/null; then
        echo -e "${GREEN}✓ Server started successfully (PID: $(pgrep -f 'python app.py'))${NC}"
        echo -e "${BLUE}Logs: tail -f server.log${NC}"
        echo -e "${BLUE}Test: python test_client.py${NC}"
        echo -e "${BLUE}Stop: ./stop_server.sh${NC}"
    else
        echo -e "${RED}✗ Failed to start server${NC}"
        exit 1
    fi
fi

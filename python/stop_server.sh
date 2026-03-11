#!/bin/bash

# Script to stop the gRPC server
# Usage: ./stop_server.sh

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

if pgrep -f "python app.py" > /dev/null; then
    echo -e "${GREEN}Stopping gRPC server...${NC}"
    pkill -f "python app.py"
    sleep 1
    
    if ! pgrep -f "python app.py" > /dev/null; then
        echo -e "${GREEN}✓ Server stopped${NC}"
    else
        echo -e "${RED}✗ Failed to stop server${NC}"
        exit 1
    fi
else
    echo -e "${RED}Server is not running${NC}"
fi

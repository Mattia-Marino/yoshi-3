#!/bin/bash

# Test script for GitHub Repository Extractor Server

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== GitHub Repository Extractor Server - Test Script ===${NC}\n"

# Check if YOSHI_GH_TOKEN is set
if [ -z "$YOSHI_GH_TOKEN" ]; then
    echo -e "${RED}Error: YOSHI_GH_TOKEN environment variable is not set${NC}"
    echo -e "Please set it with: ${GREEN}export YOSHI_GH_TOKEN=\"your_token_here\"${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Environment variable YOSHI_GH_TOKEN is set"

# Check if input.csv exists
if [ ! -f "input.csv" ]; then
    echo -e "${RED}Error: input.csv not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found input.csv"

# Get absolute path to input.csv
INPUT_PATH=$(readlink -f input.csv)
echo -e "${GREEN}✓${NC} Input file path: $INPUT_PATH"

# Start the server in background
cd go || exit 1
echo -e "\n${YELLOW}Starting server...${NC}"
./github-extractor &
SERVER_PID=$!
echo -e "${GREEN}✓${NC} Server started with PID: $SERVER_PID"

# Wait for server to start
sleep 2

# Test health endpoint
echo -e "\n${YELLOW}Testing health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:8080/health)
echo -e "Response: ${GREEN}$HEALTH_RESPONSE${NC}"

# Test extract endpoint
echo -e "\n${YELLOW}Testing extract endpoint...${NC}"
echo -e "Sending request with input file: $INPUT_PATH"

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_PATH\"}" \
  | jq . > ../output.json 2>/dev/null

if [ -f "../output.json" ]; then
    echo -e "\n${GREEN}✓${NC} Response saved to output.json"
    echo -e "\n${BLUE}Summary:${NC}"
    cat ../output.json | jq -r '"Total repositories: \(.total_count)"'
    echo -e "\n${BLUE}First repository:${NC}"
    cat ../output.json | jq '.repositories[0]'
else
    echo -e "\n${RED}✗${NC} Failed to get response"
fi

# Stop the server
echo -e "\n${YELLOW}Stopping server...${NC}"
kill $SERVER_PID
echo -e "${GREEN}✓${NC} Server stopped"

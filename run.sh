#!/bin/bash

# Example script to run the GitHub Repository Extractor

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== GitHub Repository Extractor ===${NC}\n"

# Check if YOSHI-GH-TOKEN is set
if [ -z "$YOSHI_GH_TOKEN" ]; then
    echo -e "${RED}Error: YOSHI_GH_TOKEN environment variable is not set${NC}"
    echo -e "Please set it with: ${GREEN}export YOSHI_GH_TOKEN=\"your_token_here\"${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Environment variable YOSHI-GH-TOKEN is set"

# Check if input.csv exists
if [ ! -f "input.csv" ]; then
    echo -e "${RED}Error: input.csv not found${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found input.csv"

# Navigate to go directory
cd go || exit 1

echo -e "${GREEN}✓${NC} Changed to go directory"

# Check if dependencies are installed
if [ ! -f "go.sum" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    go mod download
fi

echo -e "${GREEN}✓${NC} Dependencies ready"

# Run the program
echo -e "\n${YELLOW}Running GitHub extractor...${NC}\n"
go run main.go

# Check if output was created
if [ -f "../output.csv" ]; then
    echo -e "\n${GREEN}✓${NC} Output saved to output.csv"
    echo -e "\nFirst few lines of output:"
    head -n 3 ../output.csv
else
    echo -e "\n${RED}✗${NC} Failed to create output.csv"
    exit 1
fi

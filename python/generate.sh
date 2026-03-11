#!/bin/bash

# Script to generate Python gRPC code from proto files
# Usage: ./generate.sh

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Generating gRPC Python code...${NC}"

# Determine if we're in a virtual environment
if [ -d ".venv" ]; then
    if [ -z "$VIRTUAL_ENV" ]; then
        echo -e "${BLUE}Activating virtual environment...${NC}"
        source .venv/bin/activate
    else
        echo -e "${GREEN}Virtual environment already active${NC}"
    fi
fi

# Create generated directory if it doesn't exist
mkdir -p generated

# Generate Python code from proto files
python -m grpc_tools.protoc \
    --proto_path=./protos \
    --python_out=./generated \
    --grpc_python_out=./generated \
    ./protos/processor.proto

# Create __init__.py in generated directory
touch generated/__init__.py

echo -e "${GREEN}✓ Generated files created in ./generated/${NC}"
echo -e "${GREEN}✓ processor_pb2.py${NC}"
echo -e "${GREEN}✓ processor_pb2_grpc.py${NC}"
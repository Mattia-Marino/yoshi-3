#!/bin/bash

# Generates gRPC code for both Go and Python from the shared proto file.
# Prerequisites:
#   - protoc (Protocol Buffers compiler)
#   - protoc-gen-go: go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
#   - protoc-gen-go-grpc: go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
#   - grpcio-tools (Python): pip install grpcio-tools
#
# Usage: ./generate.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROTO_DIR="$SCRIPT_DIR/protos"
GO_OUT="$SCRIPT_DIR/go/proto"
PY_OUT="$SCRIPT_DIR/python/generated"

echo "Generating gRPC code from $PROTO_DIR/processor.proto"

# --- Go ---
echo "  [Go] Generating into $GO_OUT"
mkdir -p "$GO_OUT"
protoc \
    --proto_path="$PROTO_DIR" \
    --go_out="$GO_OUT" \
    --go_opt=paths=source_relative \
    --go-grpc_out="$GO_OUT" \
    --go-grpc_opt=paths=source_relative \
    "$PROTO_DIR/processor.proto"
echo "  [Go] Done"

# --- Python ---
echo "  [Python] Generating into $PY_OUT"
mkdir -p "$PY_OUT"

# Use the venv if available
if [ -d "$SCRIPT_DIR/python/.venv" ] && [ -z "$VIRTUAL_ENV" ]; then
    source "$SCRIPT_DIR/python/.venv/bin/activate"
fi

python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$PY_OUT" \
    --grpc_python_out="$PY_OUT" \
    "$PROTO_DIR/processor.proto"
touch "$PY_OUT/__init__.py"
echo "  [Python] Done"

echo "Code generation complete."

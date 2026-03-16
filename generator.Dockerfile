FROM golang:1.24-alpine

# Install protoc and python
RUN apk add --no-cache protoc protobuf-dev python3 py3-pip bash

# Install Go plugins
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# Install Python plugins
RUN pip install --break-system-packages grpcio-tools

WORKDIR /workspace
ENTRYPOINT ["/bin/bash", "./generate.sh"]
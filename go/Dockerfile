
# Multi-stage Dockerfile for the Go REST API
# Builder stage
FROM golang:1.24.4 AS builder

WORKDIR /src

# Install protoc to generate Go sources from shared proto definitions.
RUN apt-get update && apt-get install -y --no-install-recommends protobuf-compiler && rm -rf /var/lib/apt/lists/*

# Install protoc plugins compatible with this Go version.
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest && \
	go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest

# Use Go modules; copy only go.mod and go.sum first to leverage cache
COPY go/go.mod go/go.sum ./go/

WORKDIR /src/go
RUN go mod download

# Copy source and build static binary
COPY go/ ./
COPY protos/ ../protos/

# Ensure generated messages/services are present before compiling mapper.go.
RUN protoc \
	--proto_path=../protos \
	--go_out=./proto \
	--go_opt=paths=source_relative \
	--go-grpc_out=./proto \
	--go-grpc_opt=paths=source_relative \
	../protos/processor.proto

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
	go build -trimpath -ldflags "-s -w" -o /app/server .

# Final stage: small runtime image with ca-certificates
FROM alpine:3.19
RUN apk add --no-cache ca-certificates

WORKDIR /app

# Allow passing the GitHub token from the build environment or at runtime.
# To pass at build time:  `docker build --build-arg YOSHI_GH_TOKEN="$YOSHI_GH_TOKEN" ...`
# To pass at runtime (recommended): `docker run -e YOSHI_GH_TOKEN="$YOSHI_GH_TOKEN" ...`
ARG YOSHI_GH_TOKEN
ENV YOSHI_GH_TOKEN=${YOSHI_GH_TOKEN}

# Copy the statically built binary from builder
COPY --from=builder /app/server ./server

# Expose the port the app runs on
EXPOSE 6001

ENTRYPOINT ["/app/server"]

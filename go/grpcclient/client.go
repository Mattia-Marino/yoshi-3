package grpcclient

import (
	"context"
	"fmt"
	"time"

	pb "github-extractor/proto"

	"github.com/sirupsen/logrus"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// ProcessorClient wraps the gRPC connection to the ProcessorService.
type ProcessorClient struct {
	conn   *grpc.ClientConn
	client pb.ProcessorServiceClient
	logger *logrus.Logger
}

// NewProcessorClient dials the gRPC server at the given address and returns a client.
func NewProcessorClient(addr string, logger *logrus.Logger) (*ProcessorClient, error) {
	conn, err := grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to gRPC server at %s: %w", addr, err)
	}

	logger.Infof("Connected to gRPC ProcessorService at %s", addr)

	return &ProcessorClient{
		conn:   conn,
		client: pb.NewProcessorServiceClient(conn),
		logger: logger,
	}, nil
}

// ProcessResult holds the metrics returned from the gRPC service.
type ProcessResult struct {
	Formality     float64 `json:"formality"`
	Geodispersion float64 `json:"geodispersion"`
	Longevity     float64 `json:"longevity"`
	Cohesion      float64 `json:"cohesion"`
}

// Process sends repository data to the ProcessorService and returns computed metrics.
func (pc *ProcessorClient) Process(ctx context.Context, repoProto *pb.Repository) (*ProcessResult, error) {
	req := &pb.ProcessRequest{
		Repository: repoProto,
	}

	callCtx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()

	resp, err := pc.client.Process(callCtx, req)
	if err != nil {
		return nil, fmt.Errorf("gRPC Process call failed: %w", err)
	}

	return &ProcessResult{
		Formality:     resp.Formality,
		Geodispersion: resp.Geodispersion,
		Longevity:     resp.Longevity,
		Cohesion:      resp.Cohesion,
	}, nil
}

// Close gracefully shuts down the gRPC connection.
func (pc *ProcessorClient) Close() error {
	if pc.conn != nil {
		return pc.conn.Close()
	}
	return nil
}

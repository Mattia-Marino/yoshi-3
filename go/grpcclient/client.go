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
type GeoGraphNode struct {
	Login     string  `json:"login"`
	Country   string  `json:"country"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type GeoGraphEdge struct {
	From       string  `json:"from"`
	To         string  `json:"to"`
	Type       string  `json:"type"`
	DistanceKm float64 `json:"distance_km"`
}

type GeoGraph struct {
	Nodes []GeoGraphNode `json:"nodes"`
	Edges []GeoGraphEdge `json:"edges"`
}

type ProcessResult struct {
	Formality     float64   `json:"formality"`
	Geodispersion float64   `json:"geodispersion"`
	Longevity     float64   `json:"longevity"`
	Cohesion      float64   `json:"cohesion"`
	GeoGraph      *GeoGraph `json:"geo_graph,omitempty"`
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

	result := &ProcessResult{
		Formality:     resp.Formality,
		Geodispersion: resp.Geodispersion,
		Longevity:     resp.Longevity,
		Cohesion:      resp.Cohesion,
	}
	if resp.GeoGraph != nil {
		geo := &GeoGraph{}
		for _, n := range resp.GeoGraph.Nodes {
			geo.Nodes = append(geo.Nodes, GeoGraphNode{
				Login:     n.Login,
				Country:   n.Country,
				Latitude:  n.Latitude,
				Longitude: n.Longitude,
			})
		}
		for _, e := range resp.GeoGraph.Edges {
			geo.Edges = append(geo.Edges, GeoGraphEdge{
				From:       e.From,
				To:         e.To,
				Type:       e.Type,
				DistanceKm: e.DistanceKm,
			})
		}
		if geo.Nodes == nil {
			geo.Nodes = []GeoGraphNode{}
		}
		if geo.Edges == nil {
			geo.Edges = []GeoGraphEdge{}
		}
		result.GeoGraph = geo
	}

	return result, nil
}

// Close gracefully shuts down the gRPC connection.
func (pc *ProcessorClient) Close() error {
	if pc.conn != nil {
		return pc.conn.Close()
	}
	return nil
}

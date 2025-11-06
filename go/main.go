package main

import (
	"fmt"
	"log"
	"net/http"
	"runtime"

	"github-extractor/config"
	"github-extractor/github"
	"github-extractor/server"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Configuration error: %v", err)
	}

	// Set GOMAXPROCS to use all available CPU cores
	numCPU := runtime.NumCPU()
	runtime.GOMAXPROCS(numCPU)

	log.Printf("GitHub Repository Extractor Server")
	log.Printf("Using %d CPU cores for parallel processing", numCPU)

	// Create GitHub client
	ghClient := github.NewClient(cfg.GitHubToken)

	// Create HTTP handler
	handler := server.NewHandler(ghClient)

	// Register routes
	http.HandleFunc("/extract", handler.ExtractHandler)
	http.HandleFunc("/health", healthCheckHandler)

	// Start server
	address := fmt.Sprintf(":%s", cfg.Port)
	log.Printf("Server starting on %s", address)
	log.Printf("Endpoint: GET /extract")
	log.Printf("Health check: GET /health")

	if err := http.ListenAndServe(address, nil); err != nil {
		log.Fatalf("Server failed to start: %v", err)
	}
}

// healthCheckHandler handles health check requests
func healthCheckHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"status":"ok","cores":%d}`, runtime.NumCPU())
}

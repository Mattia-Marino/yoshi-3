package server

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"runtime"
	"sync"

	"github-extractor/csv"
	"github-extractor/github"
	"github-extractor/models"
)

// Request represents the incoming HTTP request payload
type Request struct {
	InputFilePath string `json:"input_file_path"`
}

// Response represents the response containing all repository information
type Response struct {
	Repositories []models.RepositoryInfo `json:"repositories"`
	TotalCount   int                     `json:"total_count"`
	Error        string                  `json:"error,omitempty"`
}

// Handler handles HTTP requests for repository extraction
type Handler struct {
	ghClient *github.Client
}

// NewHandler creates a new HTTP handler
func NewHandler(ghClient *github.Client) *Handler {
	return &Handler{
		ghClient: ghClient,
	}
}

// HealthCheckHandler handles health check requests
func (h *Handler) HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"status":"ok","cores":%d}`, runtime.NumCPU())
}

// ExtractHandler handles the GET request for extracting repository information
func (h *Handler) ExtractHandler(w http.ResponseWriter, r *http.Request) {
	// Only accept GET requests
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse JSON body
	var req Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
		return
	}

	if req.InputFilePath == "" {
		respondWithError(w, http.StatusBadRequest, "input_file_path is required")
		return
	}

	// Read repositories from CSV
	reader := csv.NewReader(req.InputFilePath)
	repositories, err := reader.ReadRepositories()
	if err != nil {
		respondWithError(w, http.StatusBadRequest, fmt.Sprintf("Failed to read input file: %v", err))
		return
	}

	if len(repositories) == 0 {
		respondWithJSON(w, http.StatusOK, Response{
			Repositories: []models.RepositoryInfo{},
			TotalCount:   0,
		})
		return
	}

	// Process repositories in parallel using all available CPU cores
	log.Printf("Processing %d repositories using %d CPU cores", len(repositories), runtime.NumCPU())
	results := h.processRepositoriesParallel(repositories)

	// Respond with JSON
	respondWithJSON(w, http.StatusOK, Response{
		Repositories: results,
		TotalCount:   len(results),
	})
}

// processRepositoriesParallel processes repositories in parallel, one per CPU core
func (h *Handler) processRepositoriesParallel(repositories []models.RepositoryInput) []models.RepositoryInfo {
	numWorkers := runtime.NumCPU()
	jobs := make(chan models.RepositoryInput, len(repositories))
	results := make(chan models.RepositoryInfo, len(repositories))

	// Start worker pool
	var wg sync.WaitGroup
	for i := 0; i < numWorkers; i++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			for repo := range jobs {
				log.Printf("[Worker %d] Processing %s/%s", workerID, repo.Owner, repo.Repo)
				info := h.ghClient.GetRepositoryInfo(repo.Owner, repo.Repo)
				results <- info
			}
		}(i)
	}

	// Send jobs to workers
	go func() {
		for _, repo := range repositories {
			jobs <- repo
		}
		close(jobs)
	}()

	// Wait for all workers to finish
	go func() {
		wg.Wait()
		close(results)
	}()

	// Collect results
	var allResults []models.RepositoryInfo
	for result := range results {
		allResults = append(allResults, result)
	}

	return allResults
}

// respondWithJSON writes a JSON response
func respondWithJSON(w http.ResponseWriter, statusCode int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Printf("Error encoding JSON response: %v", err)
	}
}

// respondWithError writes an error JSON response
func respondWithError(w http.ResponseWriter, statusCode int, message string) {
	respondWithJSON(w, statusCode, Response{
		Error: message,
	})
}

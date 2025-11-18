package server

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"runtime"

	"github-extractor/models"
)

// ExtractRequest represents the incoming HTTP request payload
type ExtractRequest struct {
	Owner string `json:"owner"`
	Repo  string `json:"repo"`
}

// ExtractResponse represents the response containing repository information
type ExtractResponse struct {
	Repository models.RepositoryInfo `json:"repository"`
	Error      string                `json:"error,omitempty"`
}

// Handler handles HTTP requests for repository extraction
type Handler struct {
	service *Service
}

// NewHandler creates a new HTTP handler
func NewHandler(service *Service) *Handler {
	return &Handler{
		service: service,
	}
}

// HealthCheckHandler handles health check requests
func (h *Handler) HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"status":"ok","cores":%d}`, runtime.NumCPU())
}

// ExtractHandler handles the POST request for extracting repository information
func (h *Handler) ExtractHandler(w http.ResponseWriter, r *http.Request) {
	// Only accept POST requests
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse JSON body
	var req ExtractRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		respondWithError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
		return
	}

	// Validate required fields
	if req.Owner == "" {
		respondWithError(w, http.StatusBadRequest, "owner is required")
		return
	}
	if req.Repo == "" {
		respondWithError(w, http.StatusBadRequest, "repo is required")
		return
	}

	// Process repository using the service (will be assigned to a free worker)
	result := h.service.ProcessRepository(req.Owner, req.Repo)

	// Respond with JSON
	respondWithJSON(w, http.StatusOK, ExtractResponse{
		Repository: result,
	})
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
	respondWithJSON(w, statusCode, ExtractResponse{
		Error: message,
	})
}

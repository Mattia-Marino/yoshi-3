package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"runtime"

	"github-extractor/models"

	"github.com/sirupsen/logrus"
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
	logger  *logrus.Logger
}

// NewHandler creates a new HTTP handler
func NewHandler(service *Service, logger *logrus.Logger) *Handler {
	return &Handler{
		service: service,
		logger:  logger,
	}
}

// HealthCheckHandler handles health check requests
// @Summary Health check
// @Description Checks if the server is running and returns the number of cores.
// @Tags health
// @Produce json
// @Success 200 {object} map[string]interface{}
// @Router /health [get]
func (h *Handler) HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"status":"ok","cores":%d}`, runtime.NumCPU())
}

// ExtractHandler handles the POST request for extracting repository information
// @Summary Extract repository information
// @Description Extracts detailed information about a GitHub repository including commits, milestones, and contributors.
// @Tags repository
// @Accept json
// @Produce json
// @Param request body ExtractRequest true "Repository extraction request"
// @Success 200 {object} ExtractResponse
// @Failure 400 {object} ExtractResponse "Invalid request"
// @Failure 422 {object} ExtractResponse "Repository not eligible"
// @Failure 500 {object} ExtractResponse "Internal server error"
// @Router /extract [post]
func (h *Handler) ExtractHandler(w http.ResponseWriter, r *http.Request) {
	// Only accept POST requests
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse JSON body
	var req ExtractRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.respondWithError(w, http.StatusBadRequest, fmt.Sprintf("Invalid JSON: %v", err))
		return
	}

	// Validate required fields
	if req.Owner == "" {
		h.respondWithError(w, http.StatusBadRequest, "owner is required")
		return
	}
	if req.Repo == "" {
		h.respondWithError(w, http.StatusBadRequest, "repo is required")
		return
	}

	// Use the client from the service
	gh := h.service.ghClient

	// Run fast eligibility checks first (100 commits, last 90 days, 10 active contributors)
	ok, reason, err := gh.CheckRepoEligibility(req.Owner, req.Repo, 100, 90, 10)
	if err != nil {
		h.logger.Errorf("Error checking eligibility for %s/%s: %v", req.Owner, req.Repo, err)
		http.Error(w, "internal error checking repository eligibility: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if !ok {
		h.logger.Infof("Repository %s/%s not eligible: %s", req.Owner, req.Repo, reason)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity) // 422
		_ = json.NewEncoder(w).Encode(map[string]string{"error": reason})
		return
	}

	// --- existing code continues only if checks passed ---
	// Process repository using the service (will be assigned to a free worker)
	result := h.service.ProcessRepository(req.Owner, req.Repo)

	// Respond with JSON
	h.respondWithJSON(w, http.StatusOK, ExtractResponse{
		Repository: result,
	})
}

// respondWithJSON writes a JSON response
func (h *Handler) respondWithJSON(w http.ResponseWriter, statusCode int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		h.logger.Errorf("Error encoding JSON response: %v", err)
	}
}

// respondWithError writes an error JSON response
func (h *Handler) respondWithError(w http.ResponseWriter, statusCode int, message string) {
	h.respondWithJSON(w, statusCode, ExtractResponse{
		Error: message,
	})
}

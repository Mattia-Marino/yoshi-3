package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"runtime"

	"github-extractor/grpcclient"
	"github-extractor/models"
	pb "github-extractor/proto"

	"github.com/sirupsen/logrus"
)

// ExtractRequest represents the incoming HTTP request payload
type ExtractRequest struct {
	Owner      string `json:"owner"`
	Repo       string `json:"repo"`
	MinCommits *int   `json:"min_commits,omitempty"`
	Days       *int   `json:"days,omitempty"`
	MinActive  *int   `json:"min_active,omitempty"`
}

const (
	defaultMinCommits = 1
	defaultDays       = 1000
	defaultMinActive  = 1
)

func resolveEligibilityParams(req ExtractRequest) (int, int, int, error) {
	minCommits := defaultMinCommits
	days := defaultDays
	minActive := defaultMinActive

	if req.MinCommits != nil {
		if *req.MinCommits <= 0 {
			return 0, 0, 0, fmt.Errorf("min_commits must be greater than 0")
		}
		minCommits = *req.MinCommits
	}

	if req.Days != nil {
		if *req.Days <= 0 {
			return 0, 0, 0, fmt.Errorf("days must be greater than 0")
		}
		days = *req.Days
	}

	if req.MinActive != nil {
		if *req.MinActive <= 0 {
			return 0, 0, 0, fmt.Errorf("min_active must be greater than 0")
		}
		minActive = *req.MinActive
	}

	return minCommits, days, minActive, nil
}

// ExtractResponse represents the response containing repository information
type ExtractResponse struct {
	Repository models.RepositoryInfo `json:"repository"`
	Error      string                `json:"error,omitempty"`
}

// ExtractResponseLimits represents the response containing rate limits information
type ExtractResponseLimits struct {
	Remaining int    `json:"remaining"`
	Error     string `json:"error,omitempty"`
}

// Handler handles HTTP requests for repository extraction
type Handler struct {
	service         *Service
	logger          *logrus.Logger
	processorClient *grpcclient.ProcessorClient
}

// NewHandler creates a new HTTP handler
func NewHandler(service *Service, logger *logrus.Logger, processorClient *grpcclient.ProcessorClient) *Handler {
	return &Handler{
		service:         service,
		logger:          logger,
		processorClient: processorClient,
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

// GetRemainingRequestsHandler handles the count of the remaining requests available
// @Summary Get remaining requests
// @Description Gives the number of the remaining GitHub API requests available
// @Tags remaining
// @Produce json
// @Success 200 {object} ExtractResponseLimits
// @Failure 400 {object} ExtractResponse "Invalid request"
// @Router /remaining [get]
func (h *Handler) GetRemainingRequestsHandler(w http.ResponseWriter, r *http.Request) {
	gh := h.service.ghClient
	rate, err := gh.GetRemainingRequests()

	if err != nil {
		h.respondWithError(w, http.StatusBadRequest, "Invalid request")
	}

	h.respondWithJSON(w, http.StatusOK, ExtractResponseLimits{
		Remaining: rate,
	})
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

	minCommits, days, minActive, err := resolveEligibilityParams(req)
	if err != nil {
		h.respondWithError(w, http.StatusBadRequest, err.Error())
		return
	}

	// Use the client from the service
	gh := h.service.ghClient

	// Run eligibility checks using user-provided thresholds or defaults.
	ok, reason, err := gh.CheckRepoEligibility(req.Owner, req.Repo, minCommits, days, minActive)
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

// ProcessHandlerResponse represents the response from the /process endpoint
type ProcessHandlerResponse struct {
	Formality     float64 `json:"formality"`
	Geodispersion float64 `json:"geodispersion"`
	Longevity     float64 `json:"longevity"`
	Cohesion      float64 `json:"cohesion"`
	Error         string  `json:"error,omitempty"`
}

// ProcessHandler handles the POST request for extracting and processing repository metrics
// @Summary Process repository metrics
// @Description Extracts repository data and computes formality, geodispersion, and longevity metrics.
// @Tags repository
// @Accept json
// @Produce json
// @Param request body ExtractRequest true "Repository process request"
// @Success 200 {object} ProcessHandlerResponse
// @Failure 400 {object} ProcessHandlerResponse "Invalid request"
// @Failure 422 {object} ProcessHandlerResponse "Repository not eligible"
// @Failure 500 {object} ProcessHandlerResponse "Internal server error"
// @Router /process [post]
func (h *Handler) ProcessHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req ExtractRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.respondWithJSON(w, http.StatusBadRequest, ProcessHandlerResponse{Error: fmt.Sprintf("Invalid JSON: %v", err)})
		return
	}

	if req.Owner == "" {
		h.respondWithJSON(w, http.StatusBadRequest, ProcessHandlerResponse{Error: "owner is required"})
		return
	}
	if req.Repo == "" {
		h.respondWithJSON(w, http.StatusBadRequest, ProcessHandlerResponse{Error: "repo is required"})
		return
	}

	minCommits, days, minActive, err := resolveEligibilityParams(req)
	if err != nil {
		h.respondWithJSON(w, http.StatusBadRequest, ProcessHandlerResponse{Error: err.Error()})
		return
	}

	if h.processorClient == nil {
		h.respondWithJSON(w, http.StatusInternalServerError, ProcessHandlerResponse{Error: "processor service not configured"})
		return
	}

	gh := h.service.ghClient

	ok, reason, err := gh.CheckRepoEligibility(req.Owner, req.Repo, minCommits, days, minActive)
	if err != nil {
		h.logger.Errorf("Error checking eligibility for %s/%s: %v", req.Owner, req.Repo, err)
		h.respondWithJSON(w, http.StatusInternalServerError, ProcessHandlerResponse{Error: "internal error checking repository eligibility: " + err.Error()})
		return
	}
	if !ok {
		h.logger.Infof("Repository %s/%s not eligible: %s", req.Owner, req.Repo, reason)
		h.respondWithJSON(w, http.StatusUnprocessableEntity, ProcessHandlerResponse{Error: reason})
		return
	}

	// Extract repository info (same as /extract)
	repoInfo := h.service.ProcessRepository(req.Owner, req.Repo)
	if repoInfo.Error != "" {
		h.respondWithJSON(w, http.StatusInternalServerError, ProcessHandlerResponse{Error: fmt.Sprintf("extraction failed: %s", repoInfo.Error)})
		return
	}

	// Convert to proto message
	repoProto := pb.RepositoryInfoToProto(repoInfo)

	// Call gRPC ProcessorService
	metrics, err := h.processorClient.Process(r.Context(), repoProto)
	if err != nil {
		h.logger.Errorf("gRPC Process failed for %s/%s: %v", req.Owner, req.Repo, err)
		h.respondWithJSON(w, http.StatusInternalServerError, ProcessHandlerResponse{Error: fmt.Sprintf("processing failed: %v", err)})
		return
	}

	h.respondWithJSON(w, http.StatusOK, ProcessHandlerResponse{
		Formality:     metrics.Formality,
		Geodispersion: metrics.Geodispersion,
		Longevity:     metrics.Longevity,
		Cohesion:      metrics.Cohesion,
	})
}

package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"runtime"
	"sort"

	"github-extractor/github"
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
	defaultMinCommits = 1500
	defaultDays       = 90
	defaultMinActive  = 3
)

func resolveEligibilityParams(req ExtractRequest) (int, int, int, error) {
	minCommits := defaultMinCommits
	days := defaultDays
	minActive := defaultMinActive

	if req.MinCommits != nil {
		if *req.MinCommits < 0 {
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
		if *req.MinActive < 0 {
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
		h.logger.Errorf("GetRemainingRequests failed: %v", err)
		h.respondWithJSON(w, http.StatusBadGateway, ExtractResponseLimits{
			Remaining: rate,
			Error:     err.Error(),
		})
		return
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
	status, reason, details, err := gh.CheckRepoEligibility(req.Owner, req.Repo, minCommits, days, minActive)
	if err != nil {
		h.logger.Errorf("Error checking eligibility for %s/%s: %v", req.Owner, req.Repo, err)
		http.Error(w, "internal error checking repository eligibility: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if status != github.EligibilityEligible {
		h.logger.Infof("Repository %s/%s not eligible (%s): %s", req.Owner, req.Repo, status, reason)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity) // 422
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"error":            reason,
			"status":           string(status),
			"commits_found":    details.CommitCount,
			"commits_required": details.MinCommits,
			"active_found":     details.ActiveCount,
			"active_required":  details.MinActive,
			"days":             details.Days,
		})
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
type CohesionGraphNode struct {
	ID        string  `json:"id"`
	Label     string  `json:"label"`
	Followers int     `json:"followers"`
	Following int     `json:"following"`
	Ratio     float64 `json:"ratio"`
}

type CohesionGraphEdge struct {
	From string `json:"from"`
	To   string `json:"to"`
	Type string `json:"type"`
}

type CohesionGraph struct {
	Nodes []CohesionGraphNode `json:"nodes"`
	Edges []CohesionGraphEdge `json:"edges"`
}

type GeoProximityNode struct {
	Login     string  `json:"login"`
	Country   string  `json:"country"`
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}

type GeoProximityEdge struct {
	From       string  `json:"from"`
	To         string  `json:"to"`
	Type       string  `json:"type"`
	DistanceKm float64 `json:"distance_km"`
}

type GeoProximityGraph struct {
	Nodes []GeoProximityNode `json:"nodes"`
	Edges []GeoProximityEdge `json:"edges"`
}

// ---------------------------------------------------------------------------
// Grafo di co-attivita temporale (teoria):
// - NON dice "chi segue chi" (quello e il grafo di coesione, relazione
//   dichiarata e permanente), ma "chi codifica insieme a chi, quando"
//   (collaborazione praticata nel tempo).
// - Due contributor collegati hanno committato nelle stesse settimane: con
//   buona probabilita lavoravano sullo stesso stato del progetto.
// - Come leggerlo: nucleo denso = team reale (ma fragile se piccolo);
//   nodi isolati = comparse one-shot (problema di retention, non di
//   visibilita); gruppetti separati = sottogruppi/silos; archi che si
//   spostano dai vecchi ai nuovi = passaggio di testimone sano.
// - Coesione alta + co-attivita frammentata = folla di solisti, non un team.
// ---------------------------------------------------------------------------
type CoActivityNode struct {
	ID           string `json:"id"`
	Label        string `json:"label"`
	ActiveWeeks  int    `json:"active_weeks"`
	TotalCommits int    `json:"total_commits"`
}

type CoActivityEdge struct {
	From   string `json:"from"`
	To     string `json:"to"`
	Type   string `json:"type"`
	Weight int    `json:"weight"`
}

type CoActivityGraph struct {
	Nodes []CoActivityNode `json:"nodes"`
	Edges []CoActivityEdge `json:"edges"`
}

// maxCoActivityNodes limita i nodi ai piu attivi per commit: oltre questa
// soglia il grafo diventa illeggibile e la risposta /process troppo pesante.
// Gli esclusi sono quasi sempre comparse con 1-2 commit (nodi isolati).
const maxCoActivityNodes = 60

type ProcessHandlerResponse struct {
	Formality       float64 `json:"formality"`
	Geodispersion   float64 `json:"geodispersion"`
	Longevity       float64 `json:"longevity"`
	Cohesion        float64 `json:"cohesion"`
	SimpleProject   bool    `json:"simple_project,omitempty"`
	Category        string  `json:"category,omitempty"`
	Inactive        bool    `json:"inactive,omitempty"`
	Reason          string  `json:"reason,omitempty"`
	CommitsFound    int           `json:"commits_found"`
	CommitsRequired int           `json:"commits_required"`
	ActiveFound     int           `json:"active_found"`
	ActiveRequired  int           `json:"active_required"`
	Days            int           `json:"days"`
	CohesionGraph   *CohesionGraph `json:"cohesion_graph,omitempty"`
	GeoGraph        *GeoProximityGraph `json:"geo_graph,omitempty"`
	CoActivityGraph *CoActivityGraph `json:"coactivity_graph,omitempty"`
	Error           string        `json:"error,omitempty"`
}

func buildCohesionGraph(repoInfo models.RepositoryInfo) *CohesionGraph {
	// Nodi = TUTTA la community (anche senza location). Le metriche Python
	// restano sul sottoinsieme con location: il punteggio non cambia, ma il
	// grafo non si svuota sui repo con poche location compilate.
	members := repoInfo.CommunityContributors
	if len(members) == 0 {
		members = repoInfo.Contributors
	}
	nodes := make([]CohesionGraphNode, 0, len(members))
	for _, c := range members {
		nodes = append(nodes, CohesionGraphNode{
			ID:        c.Login,
			Label:     c.Login,
			Followers: c.Followers,
			Following: c.Following,
			Ratio:     c.FollowerFollowingRatio,
		})
	}
	edges := make([]CohesionGraphEdge, 0, len(repoInfo.FollowEdges))
	for _, e := range repoInfo.FollowEdges {
		edges = append(edges, CohesionGraphEdge{From: e.From, To: e.To, Type: "follows"})
	}
	return &CohesionGraph{Nodes: nodes, Edges: edges}
}

func buildGeoProximityGraph(metrics *grpcclient.ProcessResult, repoInfo models.RepositoryInfo) *GeoProximityGraph {
	nodes := []GeoProximityNode{}
	edges := []GeoProximityEdge{}
	if metrics != nil && metrics.GeoGraph != nil {
		for _, n := range metrics.GeoGraph.Nodes {
			nodes = append(nodes, GeoProximityNode{
				Login:     n.Login,
				Country:   n.Country,
				Latitude:  n.Latitude,
				Longitude: n.Longitude,
			})
		}
		for _, e := range metrics.GeoGraph.Edges {
			edges = append(edges, GeoProximityEdge{
				From:       e.From,
				To:         e.To,
				Type:       e.Type,
				DistanceKm: e.DistanceKm,
			})
		}
	}
	// Chi non ha location (o non matchabile su cities.csv) non puo stare
	// sulla mappa, ma va mostrato lo stesso: nodi grigi isolati di tipo
	// "unknown". Cosi il grafo non si svuota e si vede quanta community
	// resta fuori dall'analisi geografica.
	placed := make(map[string]struct{}, len(nodes))
	for _, n := range nodes {
		placed[n.Login] = struct{}{}
	}
	members := repoInfo.CommunityContributors
	if len(members) == 0 {
		members = repoInfo.Contributors
	}
	for _, c := range members {
		if _, ok := placed[c.Login]; ok {
			continue
		}
		nodes = append(nodes, GeoProximityNode{Login: c.Login, Country: "unknown"})
		placed[c.Login] = struct{}{}
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].Login < nodes[j].Login })
	return &GeoProximityGraph{Nodes: nodes, Edges: edges}
}

// buildCoActivityGraph costruisce la rete di collaborazione temporale.
// Per ogni contributor considera l'insieme delle settimane attive (da
// ContributorStats, gia scaricato nello scraping unico: zero quota extra).
// Un arco "co_active" A-B con peso N significa: A e B hanno committato
// insieme in N settimane. Sviluppo futuro: pesare con Jaccard
// (|A∩B|/|A∪B|) per premiare chi lavora *sempre* insieme rispetto a chi si
// incrocia una volta sola.
func buildCoActivityGraph(repoInfo models.RepositoryInfo) *CoActivityGraph {
	stats := append([]models.ContributorStats(nil), repoInfo.ContributorStats...)
	sort.Slice(stats, func(i, j int) bool {
		if stats[i].Total == stats[j].Total {
			return stats[i].Author < stats[j].Author
		}
		return stats[i].Total > stats[j].Total
	})
	if len(stats) > maxCoActivityNodes {
		stats = stats[:maxCoActivityNodes]
	}

	activeWeeks := make(map[string]map[int64]struct{}, len(stats))
	totals := make(map[string]int, len(stats))
	for _, s := range stats {
		set, ok := activeWeeks[s.Author]
		if !ok {
			set = make(map[int64]struct{})
			activeWeeks[s.Author] = set
		}
		for _, w := range s.Weeks {
			if w.Commits > 0 {
				set[w.WeekTimestamp] = struct{}{}
			}
		}
		totals[s.Author] += s.Total
	}

	nodes := make([]CoActivityNode, 0, len(activeWeeks))
	for author, set := range activeWeeks {
		nodes = append(nodes, CoActivityNode{
			ID:           author,
			Label:        author,
			ActiveWeeks:  len(set),
			TotalCommits: totals[author],
		})
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].ID < nodes[j].ID })

	edges := []CoActivityEdge{}
	for i := range nodes {
		for j := i + 1; j < len(nodes); j++ {
			overlap := 0
			setA, setB := activeWeeks[nodes[i].ID], activeWeeks[nodes[j].ID]
			if len(setA) > len(setB) {
				setA, setB = setB, setA
			}
			for week := range setA {
				if _, ok := setB[week]; ok {
					overlap++
				}
			}
			if overlap > 0 {
				edges = append(edges, CoActivityEdge{
					From:   nodes[i].ID,
					To:     nodes[j].ID,
					Type:   "co_active",
					Weight: overlap,
				})
			}
		}
	}
	return &CoActivityGraph{Nodes: nodes, Edges: edges}
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

	status, reason, details, err := gh.CheckRepoEligibility(req.Owner, req.Repo, minCommits, days, minActive)
	if err != nil {
		h.logger.Errorf("Error checking eligibility for %s/%s: %v", req.Owner, req.Repo, err)
		h.respondWithJSON(w, http.StatusInternalServerError, ProcessHandlerResponse{Error: "internal error checking repository eligibility: " + err.Error()})
		return
	}
	if status == github.EligibilitySimpleProject {
		h.logger.Infof("Repository %s/%s not eligible: %s", req.Owner, req.Repo, reason)
		h.respondWithJSON(w, http.StatusOK, ProcessHandlerResponse{
			SimpleProject:   true,
			Category:        "Simple Project (SP)",
			Reason:          reason,
			CommitsFound:    details.CommitCount,
			CommitsRequired: details.MinCommits,
			ActiveFound:     details.ActiveCount,
			ActiveRequired:  details.MinActive,
			Days:            details.Days,
		})
		return
	}
	if status == github.EligibilityInactive {
		h.logger.Infof("Repository %s/%s inactive: %s", req.Owner, req.Repo, reason)
		h.respondWithJSON(w, http.StatusOK, ProcessHandlerResponse{
			Inactive:        true,
			Category:        "Inactive",
			Reason:          reason,
			CommitsFound:    details.CommitCount,
			CommitsRequired: details.MinCommits,
			ActiveFound:     details.ActiveCount,
			ActiveRequired:  details.MinActive,
			Days:            details.Days,
		})
		return
	}
	if status == github.EligibilityInactiveSP {
		h.logger.Infof("Repository %s/%s inactive simple project: %s", req.Owner, req.Repo, reason)
		h.respondWithJSON(w, http.StatusOK, ProcessHandlerResponse{
			SimpleProject:   true,
			Inactive:        true,
			Category:        "Inactive Simple Project (ISP)",
			Reason:          reason,
			CommitsFound:    details.CommitCount,
			CommitsRequired: details.MinCommits,
			ActiveFound:     details.ActiveCount,
			ActiveRequired:  details.MinActive,
			Days:            details.Days,
		})
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
		Formality:       metrics.Formality,
		Geodispersion:   metrics.Geodispersion,
		Longevity:       metrics.Longevity,
		Cohesion:        metrics.Cohesion,
		CommitsFound:    details.CommitCount,
		CommitsRequired: details.MinCommits,
		ActiveFound:     details.ActiveCount,
		ActiveRequired:  details.MinActive,
		Days:            details.Days,
		CohesionGraph:   buildCohesionGraph(repoInfo),
		GeoGraph:        buildGeoProximityGraph(metrics, repoInfo),
		CoActivityGraph: buildCoActivityGraph(repoInfo),
	})
}

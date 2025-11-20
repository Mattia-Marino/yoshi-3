package server

import (
	"runtime"

	"github-extractor/github"
	"github-extractor/models"

	"github.com/sirupsen/logrus"
)

// Service handles business logic for repository extraction
type Service struct {
	ghClient *github.Client
	jobQueue chan RepositoryRequest
	workers  int
	logger   *logrus.Logger
}

// RepositoryRequest represents a single repository extraction request
type RepositoryRequest struct {
	Owner      string
	Repo       string
	ResultChan chan models.RepositoryInfo
}

// NewService creates a new service with a worker pool
func NewService(ghClient *github.Client, logger *logrus.Logger) *Service {
	numWorkers := runtime.NumCPU()
	service := &Service{
		ghClient: ghClient,
		jobQueue: make(chan RepositoryRequest, 100), // Buffer for incoming requests
		workers:  numWorkers,
		logger:   logger,
	}

	// Start worker pool
	service.startWorkers()

	logger.Infof("Service initialized with %d workers", numWorkers)
	return service
}

// startWorkers initializes the worker pool
func (s *Service) startWorkers() {
	for i := 0; i < s.workers; i++ {
		go s.worker(i)
	}
}

// worker processes repository extraction requests
func (s *Service) worker(id int) {
	for req := range s.jobQueue {
		s.logger.Debugf("[Worker %d] Processing %s/%s", id, req.Owner, req.Repo)
		info := s.ghClient.GetRepositoryInfo(req.Owner, req.Repo)
		req.ResultChan <- info
	}
}

// ProcessRepository submits a repository for processing and waits for the result
func (s *Service) ProcessRepository(owner, repo string) models.RepositoryInfo {
	resultChan := make(chan models.RepositoryInfo, 1)

	request := RepositoryRequest{
		Owner:      owner,
		Repo:       repo,
		ResultChan: resultChan,
	}

	// Submit job to queue
	s.jobQueue <- request

	// Wait for result
	result := <-resultChan
	close(resultChan)

	return result
}

// GetWorkerCount returns the number of active workers
func (s *Service) GetWorkerCount() int {
	return s.workers
}

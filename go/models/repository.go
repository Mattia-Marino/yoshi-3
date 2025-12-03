package models

import (
	"time"
)

// RepositoryInfo contains all information about a GitHub repository
type RepositoryInfo struct {
	Owner                         string              `json:"owner"`
	Repo                          string              `json:"repo"`
	Description                   string              `json:"description"`
	Stars                         int                 `json:"stars"`
	Forks                         int                 `json:"forks"`
	OpenIssues                    int                 `json:"open_issues"`
	Language                      string              `json:"language"`
	CreatedAt                     time.Time           `json:"created_at"`
	UpdatedAt                     time.Time           `json:"updated_at"`
	Commits                       int                 `json:"commits"`
	Milestones                    int                 `json:"milestones"`
	Contributors                  []ContributorDetail `json:"contributors"`
	TotalContributorsCount        int                 `json:"total_contributors_count"`
	NonAnonymousContributorsCount int                 `json:"non_anonymous_contributors_count"`
	SelectedContributorsCount     int                 `json:"selected_contributors_count"`
	ContributorsWithLocationCount int                 `json:"contributors_with_location_count"`
	Size                          int                 `json:"size"`
	Watchers                      int                 `json:"watchers"`
	HasIssues                     bool                `json:"has_issues"`
	HasWiki                       bool                `json:"has_wiki"`
	DefaultBranch                 string              `json:"default_branch"`
	License                       string              `json:"license"`
	Error                         string              `json:"error,omitempty"`
}

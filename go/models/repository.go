package models

import (
	"fmt"
	"time"
)

// RepositoryInput represents a repository from the input CSV
type RepositoryInput struct {
	Owner string
	Repo  string
}

// RepositoryInfo contains all information about a GitHub repository
type RepositoryInfo struct {
	Owner         string
	Repo          string
	Description   string
	Stars         int
	Forks         int
	OpenIssues    int
	Language      string
	CreatedAt     time.Time
	UpdatedAt     time.Time
	Commits       int
	Milestones    int
	Size          int
	Watchers      int
	HasIssues     bool
	HasWiki       bool
	DefaultBranch string
	License       string
	Error         string
}

// ToCSVHeaders returns the CSV headers for RepositoryInfo
func (r *RepositoryInfo) ToCSVHeaders() []string {
	return []string{
		"Owner",
		"Repo",
		"Description",
		"Stars",
		"Forks",
		"OpenIssues",
		"Language",
		"CreatedAt",
		"UpdatedAt",
		"Commits",
		"Milestones",
		"Size",
		"Watchers",
		"HasIssues",
		"HasWiki",
		"DefaultBranch",
		"License",
		"Error",
	}
}

// ToCSVRow returns a row of data for CSV output
func (r *RepositoryInfo) ToCSVRow() []string {
	license := r.License
	if license == "" {
		license = "None"
	}

	return []string{
		r.Owner,
		r.Repo,
		r.Description,
		intToString(r.Stars),
		intToString(r.Forks),
		intToString(r.OpenIssues),
		r.Language,
		r.CreatedAt.Format(time.RFC3339),
		r.UpdatedAt.Format(time.RFC3339),
		intToString(r.Commits),
		intToString(r.Milestones),
		intToString(r.Size),
		intToString(r.Watchers),
		boolToString(r.HasIssues),
		boolToString(r.HasWiki),
		r.DefaultBranch,
		license,
		r.Error,
	}
}

func intToString(i int) string {
	return fmt.Sprintf("%d", i)
}

func boolToString(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

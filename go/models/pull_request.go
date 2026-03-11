package models

import (
	"time"
)

// PullRequestInfo contains information about a pull request
type PullRequestInfo struct {
	Number    int        `json:"number"`
	Status    string     `json:"status"`
	CreatedAt *time.Time `json:"created_at"`
	ClosedAt  *time.Time `json:"closed_at"`
	MergedAt  *time.Time `json:"merged_at"`
}

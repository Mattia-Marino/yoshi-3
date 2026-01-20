package models

import (
	"time"
)

// PullRequestInfo contains information about a pull request
type PullRequestInfo struct {
	Number   int        `json:"number"`
	Status   string     `json:"status"`
	MergedAt *time.Time `json:"merged_at"`
}

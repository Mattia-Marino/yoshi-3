package models

import (
	"time"
)

// CommitInfo contains information about a commit
type CommitInfo struct {
	SHA         string    `json:"sha"`
	AuthorEmail string    `json:"author_email"`
	AuthorName  string    `json:"author_name,omitempty"`
	Date        time.Time `json:"date"`
}

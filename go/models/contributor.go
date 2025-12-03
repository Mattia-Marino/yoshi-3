package models

import (
	"time"
)

// ContributorDetail holds public profile data for a GitHub user (contributor).
type ContributorDetail struct {
	Login     string    `json:"login"`
	ID        int64     `json:"id"`
	NodeID    string    `json:"node_id"`
	AvatarURL string    `json:"avatar_url"`
	HTMLURL   string    `json:"html_url"`
	Type      string    `json:"type"`
	Name      string    `json:"name"`
	Company   string    `json:"company"`
	Blog      string    `json:"blog"`
	Location  string    `json:"location"`
	Email     string    `json:"email"`
	Bio       string    `json:"bio"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
	// Error holds an error message when retrieval for this user failed
	Error string `json:"error,omitempty"`
}

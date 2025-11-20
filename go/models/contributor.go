package models

import (
	"time"
)

// ContributorDetail holds public profile data for a GitHub user (contributor).
type ContributorDetail struct {
	Login       string    `json:"login"`
	ID          int64     `json:"id"`
	NodeID      string    `json:"node_id"`
	AvatarURL   string    `json:"avatar_url"`
	HTMLURL     string    `json:"html_url"`
	Type        string    `json:"type"`
	SiteAdmin   bool      `json:"site_admin"`
	Name        string    `json:"name"`
	Company     string    `json:"company"`
	Blog        string    `json:"blog"`
	Location    string    `json:"location"`
	Email       string    `json:"email"`
	Hireable    bool      `json:"hireable"`
	Bio         string    `json:"bio"`
	Twitter     string    `json:"twitter_username"`
	PublicRepos int       `json:"public_repos"`
	PublicGists int       `json:"public_gists"`
	Followers   int       `json:"followers"`
	Following   int       `json:"following"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
	// Error holds an error message when retrieval for this user failed
	Error string `json:"error,omitempty"`
}

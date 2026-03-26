package models

import (
	"time"
)

// ContributorDetail holds public profile data for a GitHub user (contributor).
type ContributorDetail struct {
	Login     string `json:"login"`
	ID        int64  `json:"id"`
	NodeID    string `json:"node_id"`
	AvatarURL string `json:"avatar_url"`
	HTMLURL   string `json:"html_url"`
	Type      string `json:"type"`
	Name      string `json:"name"`
	Company   string `json:"company"`
	Blog      string `json:"blog"`
	Location  string `json:"location"`
	Email     string `json:"email"`
	Bio       string `json:"bio"`
	// Followers counts how many contributors in the same extracted repository community follow this user.
	Followers int `json:"followers"`
	// Following counts how many contributors in the same extracted repository community this user follows.
	Following int `json:"following"`
	// FollowerFollowingRatio is followers/following within the same repository community and is 0 when following is 0.
	FollowerFollowingRatio float64   `json:"follower_following_ratio"`
	CreatedAt              time.Time `json:"created_at"`
	UpdatedAt              time.Time `json:"updated_at"`
	// Error holds an error message when retrieval for this user failed
	Error string `json:"error,omitempty"`
}

// ContributorStats holds aggregated statistics for a contributor from stats/contributors endpoint
type ContributorStats struct {
	Author      string    `json:"author"`       // GitHub login
	Total       int       `json:"total"`        // Total number of commits
	Weeks       []Week    `json:"weeks"`        // Weekly activity
	FirstCommit time.Time `json:"first_commit"` // Date of first commit (derived from weeks)
	LastCommit  time.Time `json:"last_commit"`  // Date of last commit (derived from weeks)
}

// Week represents weekly commit activity
type Week struct {
	WeekTimestamp int64 `json:"week"`      // Unix timestamp for start of week
	Additions     int   `json:"additions"` // Lines added
	Deletions     int   `json:"deletions"` // Lines deleted
	Commits       int   `json:"commits"`   // Number of commits
}

package models

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
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

// GetContributorsDetails fetches public profile details for the given GitHub usernames.
// If token is non-empty it will be used for Authorization header (recommended to avoid rate limits).
// The function performs requests concurrently with a small worker pool.
func GetContributorsDetails(ctx context.Context, token string, usernames []string) ([]ContributorDetail, error) {
	if len(usernames) == 0 {
		return nil, nil
	}

	client := &http.Client{Timeout: 15 * time.Second}

	// Worker pool size
	maxWorkers := 8
	sem := make(chan struct{}, maxWorkers)

	var wg sync.WaitGroup
	results := make([]ContributorDetail, len(usernames))

	for i, login := range usernames {
		wg.Add(1)
		sem <- struct{}{}
		go func(idx int, username string) {
			defer wg.Done()
			defer func() { <-sem }()

			url := fmt.Sprintf("https://api.github.com/users/%s", username)
			req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
			if err != nil {
				results[idx].Error = err.Error()
				return
			}
			if token != "" {
				req.Header.Set("Authorization", "token "+token)
			}
			req.Header.Set("Accept", "application/vnd.github.v3+json")

			resp, err := client.Do(req)
			if err != nil {
				results[idx].Error = err.Error()
				return
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				results[idx].Error = fmt.Sprintf("HTTP %d", resp.StatusCode)
				return
			}

			var d ContributorDetail
			dec := json.NewDecoder(resp.Body)
			if err := dec.Decode(&d); err != nil {
				results[idx].Error = err.Error()
				return
			}

			results[idx] = d
		}(i, login)
	}

	wg.Wait()

	// Aggregate errors (if all failed, return an error; otherwise return slice and nil)
	allFailed := true
	for _, r := range results {
		if r.Error == "" {
			allFailed = false
			break
		}
	}

	if allFailed {
		return results, fmt.Errorf("failed to fetch contributor details for all users")
	}

	return results, nil
}

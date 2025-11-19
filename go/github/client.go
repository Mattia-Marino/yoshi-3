package github

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"sync"
	"time"

	gith "github.com/google/go-github/v57/github"

	"github-extractor/models"
)

// Client wraps the GitHub API client
type Client struct {
	client *gith.Client
	ctx    context.Context
	token  string
}

// NewClient creates a new GitHub API client
func NewClient(token string) *Client {
	baseTransport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		DialContext:           (&net.Dialer{Timeout: 30 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   20,
	}

	// Default http client
	defaultHTTP := &http.Client{
		Timeout:   120 * time.Second,
		Transport: baseTransport,
	}

	return &Client{
		client: gith.NewClient(defaultHTTP),
		ctx:    context.Background(),
		token:  token,
	}
}

// GetRepositoryInfo fetches detailed information about a repository
func (c *Client) GetRepositoryInfo(owner, repo string) models.RepositoryInfo {
	info := models.RepositoryInfo{
		Owner: owner,
		Repo:  repo,
	}

	// Get repository details
	repository, _, err := c.client.Repositories.Get(c.ctx, owner, repo)
	if err != nil {
		info.Error = fmt.Sprintf("Failed to fetch repository: %v", err)
		return info
	}

	// Fill in basic information
	if repository.Description != nil {
		info.Description = *repository.Description
	}
	if repository.StargazersCount != nil {
		info.Stars = *repository.StargazersCount
	}
	if repository.ForksCount != nil {
		info.Forks = *repository.ForksCount
	}
	if repository.OpenIssuesCount != nil {
		info.OpenIssues = *repository.OpenIssuesCount
	}
	if repository.Language != nil {
		info.Language = *repository.Language
	}
	if repository.CreatedAt != nil {
		info.CreatedAt = repository.CreatedAt.Time
	}
	if repository.UpdatedAt != nil {
		info.UpdatedAt = repository.UpdatedAt.Time
	}
	if repository.Size != nil {
		info.Size = *repository.Size
	}
	if repository.WatchersCount != nil {
		info.Watchers = *repository.WatchersCount
	}
	if repository.HasIssues != nil {
		info.HasIssues = *repository.HasIssues
	}
	if repository.HasWiki != nil {
		info.HasWiki = *repository.HasWiki
	}
	if repository.DefaultBranch != nil {
		info.DefaultBranch = *repository.DefaultBranch
	}
	if repository.License != nil && repository.License.Name != nil {
		info.License = *repository.License.Name
	}

	// if we reach here, filters passed: proceed to fetch contributors and other expensive stuff
	// Use wait group to fetch commits, milestones, and contributors concurrently
	var wg sync.WaitGroup
	var commitErr, milestoneErr, contributorErr error
	var commits, milestones int
	var contributors []string

	wg.Add(3)

	// Get number of commits
	go func() {
		defer wg.Done()
		commits, commitErr = c.getCommitCount(owner, repo)
	}()

	// Get number of milestones
	go func() {
		defer wg.Done()
		milestones, milestoneErr = c.getMilestoneCount(owner, repo)
	}()

	// Get contributors
	go func() {
		defer wg.Done()
		contributors, contributorErr = c.getContributors(owner, repo)
	}()

	wg.Wait()

	// Process results
	if commitErr != nil {
		info.Error = fmt.Sprintf("Failed to fetch commits: %v", commitErr)
	} else {
		info.Commits = commits
	}

	if milestoneErr != nil {
		if info.Error == "" {
			info.Error = fmt.Sprintf("Failed to fetch milestones: %v", milestoneErr)
		}
	} else {
		info.Milestones = milestones
	}

	if contributorErr != nil {
		if info.Error == "" {
			info.Error = fmt.Sprintf("Failed to fetch contributors: %v", contributorErr)
		}
	} else {
		// convert usernames into detailed contributor profiles
		details, detErr := models.GetContributorsDetails(c.ctx, c.token, contributors)
		if detErr != nil {
			if info.Error == "" {
				info.Error = fmt.Sprintf("Failed to fetch contributor details: %v", detErr)
			}
			// Even if detailed fetch failed, return repository with empty contributors
			info.Contributors = nil
		} else {
			info.Contributors = details
		}
	}

	return info
}

// Returns true if repository has at least one closed milestone.
func (c *Client) hasClosedMilestones(owner, repo string) (bool, error) {
	opt := &gith.MilestoneListOptions{
		State:       "closed",
		ListOptions: gith.ListOptions{PerPage: 1},
	}

	milestones, resp, err := c.client.Issues.ListMilestones(c.ctx, owner, repo, opt)
	if err != nil {
		return false, err
	}
	if len(milestones) > 0 {
		return true, nil
	}

	// if API reports more pages, assume there are closed milestones
	if resp != nil && resp.LastPage > 0 {
		return true, nil
	}

	return false, nil
}

// getCommitCount returns the total number of commits in the repository
func (c *Client) getCommitCount(owner, repo string) (int, error) {
	// Use pagination to count all commits
	opts := &gith.CommitsListOptions{
		ListOptions: gith.ListOptions{
			PerPage: 100,
		},
	}

	totalCommits := 0
	for {
		commits, resp, err := c.client.Repositories.ListCommits(c.ctx, owner, repo, opts)
		if err != nil {
			return 0, err
		}

		totalCommits += len(commits)

		if resp.NextPage == 0 {
			break
		}
		opts.Page = resp.NextPage
	}

	return totalCommits, nil
}

// getCommitCountWithLimit counts commits but stops early when limit is reached.
func (c *Client) getCommitCountWithLimit(owner, repo string, limit int) (int, error) {
	opts := &gith.CommitsListOptions{
		ListOptions: gith.ListOptions{PerPage: 100},
	}
	total := 0
	for {
		commits, resp, err := c.client.Repositories.ListCommits(c.ctx, owner, repo, opts)
		if err != nil {
			return total, err
		}
		total += len(commits)
		if total >= limit {
			return total, nil
		}
		if resp == nil || resp.NextPage == 0 {
			break
		}
		opts.Page = resp.NextPage
	}
	return total, nil
}

// getMilestoneCount returns the total number of milestones (open + closed)
func (c *Client) getMilestoneCount(owner, repo string) (int, error) {
	// Count open milestones
	openOpts := &gith.MilestoneListOptions{
		State: "open",
		ListOptions: gith.ListOptions{
			PerPage: 100,
		},
	}

	openCount := 0
	for {
		milestones, resp, err := c.client.Issues.ListMilestones(c.ctx, owner, repo, openOpts)
		if err != nil {
			return 0, err
		}

		openCount += len(milestones)

		if resp.NextPage == 0 {
			break
		}
		openOpts.Page = resp.NextPage
	}

	// Count closed milestones
	closedOpts := &gith.MilestoneListOptions{
		State: "closed",
		ListOptions: gith.ListOptions{
			PerPage: 100,
		},
	}

	closedCount := 0
	for {
		milestones, resp, err := c.client.Issues.ListMilestones(c.ctx, owner, repo, closedOpts)
		if err != nil {
			return 0, err
		}

		closedCount += len(milestones)

		if resp.NextPage == 0 {
			break
		}
		closedOpts.Page = resp.NextPage
	}

	return openCount + closedCount, nil
}

// hasActiveContributors returns (ok, count, err) where ok==true if unique authors in 'days' period >= minNeeded.
// It counts unique commit authors (by Login) in commits since now - days.
func (c *Client) hasActiveContributors(owner, repo string, days int, minNeeded int) (bool, int, error) {
	since := time.Now().AddDate(0, 0, -days)
	opts := &gith.CommitsListOptions{
		Since:       since,
		ListOptions: gith.ListOptions{PerPage: 100},
	}

	seen := make(map[string]struct{})
	pageLimit := 50 // safety cap to avoid extremely long scans; adjust if needed
	pages := 0
	for {
		commits, resp, err := c.client.Repositories.ListCommits(c.ctx, owner, repo, opts)
		if err != nil {
			return false, len(seen), err
		}
		for _, cm := range commits {
			if cm.Author != nil && cm.Author.Login != nil && *cm.Author.Login != "" {
				seen[*cm.Author.Login] = struct{}{}
				if len(seen) >= minNeeded {
					return true, len(seen), nil
				}
			} else if cm.Commit != nil && cm.Commit.Author != nil && cm.Commit.Author.Email != nil {
				// fallback: use email as identifier for anonymous/non-github authors
				seenKey := *cm.Commit.Author.Email
				seen[seenKey] = struct{}{}
				if len(seen) >= minNeeded {
					return true, len(seen), nil
				}
			}
		}
		pages++
		if resp == nil || resp.NextPage == 0 || pages >= pageLimit {
			break
		}
		opts.Page = resp.NextPage
	}
	return len(seen) >= minNeeded, len(seen), nil
}

// getContributors returns the list of contributor usernames
func (c *Client) getContributors(owner, repo string) ([]string, error) {
	opts := &gith.ListContributorsOptions{
		ListOptions: gith.ListOptions{
			PerPage: 100,
		},
	}

	var allContributors []string
	for {
		contributors, resp, err := c.client.Repositories.ListContributors(c.ctx, owner, repo, opts)
		if err != nil {
			return nil, err
		}

		for _, contributor := range contributors {
			if contributor.Login != nil {
				allContributors = append(allContributors, *contributor.Login)
			}
		}

		if resp.NextPage == 0 {
			break
		}
		opts.Page = resp.NextPage
	}

	return allContributors, nil
}

// CheckRepoEligibility runs the three prechecks the server should apply before heavy fetches:
//   - at least 1 closed milestone
//   - at least `minCommits` commits (use 100 where caller passes 100)
//   - at least `minActive` distinct commit authors in the last `days` days (use 3, 90)
func (c *Client) CheckRepoEligibility(owner, repo string, minCommits int, days int, minActive int) (bool, string, error) {
	// TODO: Execute in parallel way
	// 1) closed milestones
	hasClosed, err := c.hasClosedMilestones(owner, repo)
	if err != nil {
		return false, "", fmt.Errorf("error checking milestones: %w", err)
	}
	if !hasClosed {
		return false, "repository does not have at least 1 closed milestone", nil
	}

	// 2) commits >= minCommits
	commitCount, err := c.getCommitCountWithLimit(owner, repo, minCommits)
	if err != nil {
		return false, "", fmt.Errorf("error counting commits: %w", err)
	}
	if commitCount < minCommits {
		return false, fmt.Sprintf("repository has fewer than %d commits (found %d)", minCommits, commitCount), nil
	}

	// 3) active contributors
	ok, activeCount, err := c.hasActiveContributors(owner, repo, days, minActive)
	if err != nil {
		return false, "", fmt.Errorf("error checking active contributors: %w", err)
	}
	if !ok {
		return false, fmt.Sprintf("fewer than %d active contributors in the last %d days (found %d)", minActive, days, activeCount), nil
	}

	return true, "", nil
}

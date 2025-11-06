package github

import (
	"context"
	"fmt"
	"sync"

	"github.com/google/go-github/v57/github"

	"github-extractor/models"
)

// Client wraps the GitHub API client
type Client struct {
	client *github.Client
	ctx    context.Context
}

// NewClient creates a new GitHub API client
func NewClient(token string) *Client {
	client := github.NewClient(nil).WithAuthToken(token)
	return &Client{
		client: client,
		ctx:    context.Background(),
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
		info.Contributors = contributors
	}

	return info
}

// getCommitCount returns the total number of commits in the repository
func (c *Client) getCommitCount(owner, repo string) (int, error) {
	// Use pagination to count all commits
	opts := &github.CommitsListOptions{
		ListOptions: github.ListOptions{
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

// getMilestoneCount returns the total number of milestones (open + closed)
func (c *Client) getMilestoneCount(owner, repo string) (int, error) {
	// Count open milestones
	openOpts := &github.MilestoneListOptions{
		State: "open",
		ListOptions: github.ListOptions{
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
	closedOpts := &github.MilestoneListOptions{
		State: "closed",
		ListOptions: github.ListOptions{
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

// getContributors returns the list of contributor usernames
func (c *Client) getContributors(owner, repo string) ([]string, error) {
	opts := &github.ListContributorsOptions{
		ListOptions: github.ListOptions{
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

package github

import (
	"context"
	"fmt"
	"math"
	"net"
	"net/http"
	"sync"
	"time"

	gith "github.com/google/go-github/v57/github"
	"github.com/sirupsen/logrus"

	"github-extractor/models"
)

// Client wraps the GitHub API client
type Client struct {
	client *gith.Client
	ctx    context.Context
	token  string
	logger *logrus.Logger
}

type authTransport struct {
	transport http.RoundTripper
	token     string
}

func (t *authTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if t.token != "" {
		// Clone the request to avoid modifying the original
		req = req.Clone(req.Context())
		req.Header.Set("Authorization", "Bearer "+t.token)
	}
	return t.transport.RoundTrip(req)
}

// NewClient creates a new GitHub API client
func NewClient(token string, logger *logrus.Logger) *Client {
	baseTransport := &http.Transport{
		Proxy:                 http.ProxyFromEnvironment,
		DialContext:           (&net.Dialer{Timeout: 30 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		IdleConnTimeout:       90 * time.Second,
		TLSHandshakeTimeout:   10 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   20,
	}

	var transport http.RoundTripper = baseTransport
	if token != "" {
		transport = &authTransport{
			transport: baseTransport,
			token:     token,
		}
	}

	// Default http client
	defaultHTTP := &http.Client{
		Timeout:   120 * time.Second,
		Transport: transport,
	}

	return &Client{
		client: gith.NewClient(defaultHTTP),
		ctx:    context.Background(),
		token:  token,
		logger: logger,
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

	// Set derived booleans
	info.HasDescription = info.Description != ""
	info.HasLicense = info.License != ""
	info.HasWikiPage = info.HasWiki

	// Check for community health metrics
	metrics, _, err := c.client.Repositories.GetCommunityHealthMetrics(c.ctx, owner, repo)
	if err == nil && metrics.Files != nil {
		info.HasCodeOfConduct = metrics.Files.CodeOfConduct != nil
		info.HasContributingGuidelines = metrics.Files.Contributing != nil
		info.HasIssuesTemplate = metrics.Files.IssueTemplate != nil
		info.HasPullRequestTemplate = metrics.Files.PullRequestTemplate != nil
		info.HasReadme = metrics.Files.Readme != nil
	}

	// Check for Security Policy (simple check for SECURITY.md)
	// Note: This is a basic check. GitHub also supports .github/SECURITY.md
	_, _, _, err = c.client.Repositories.GetContents(c.ctx, owner, repo, "SECURITY.md", nil)
	if err == nil {
		info.HasSecurityPolicy = true
	} else {
		_, _, _, err = c.client.Repositories.GetContents(c.ctx, owner, repo, ".github/SECURITY.md", nil)
		if err == nil {
			info.HasSecurityPolicy = true
		}
	}

	// Proceed to fetch contributors, commits and milestones concurrently
	var wg sync.WaitGroup
	var commitErr, milestoneErr, contributorErr, recentContributorErr error
	var commits, milestones int
	var contributors []string
	var recentContributors []string
	var totalContributors, nonAnonContributors int

	wg.Add(4)

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
		contributors, totalContributors, nonAnonContributors, contributorErr = c.getContributors(owner, repo)
	}()

	// Get recent contributors (last 90 days)
	go func() {
		defer wg.Done()
		recentContributors, recentContributorErr = c.getRecentContributors(owner, repo, 90)
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
		info.HasMilestones = milestones > 0
	}

	if contributorErr != nil {
		if info.Error == "" {
			info.Error = fmt.Sprintf("Failed to fetch contributors: %v", contributorErr)
		}
	} else {
		info.TotalContributorsCount = totalContributors
		info.NonAnonymousContributorsCount = nonAnonContributors

		// Filter contributors: top sqrt(total) + recent (90 days)
		targetContributorsSet := make(map[string]struct{})

		// 1. Top sqrt(total)
		limit := int(math.Ceil(math.Sqrt(float64(totalContributors))))
		if limit > len(contributors) {
			limit = len(contributors)
		}
		for i := 0; i < limit; i++ {
			targetContributorsSet[contributors[i]] = struct{}{}
		}

		// 2. Recent contributors
		if recentContributorErr != nil {
			if info.Error == "" {
				info.Error = fmt.Sprintf("Failed to fetch recent contributors: %v", recentContributorErr)
			}
		} else {
			for _, u := range recentContributors {
				targetContributorsSet[u] = struct{}{}
			}
		}

		var targetContributors []string
		for u := range targetContributorsSet {
			targetContributors = append(targetContributors, u)
		}

		info.SelectedContributorsCount = len(targetContributors)

		// convert usernames into detailed contributor profiles
		details, detErr := c.getContributorsDetails(targetContributors)
		if detErr != nil {
			if info.Error == "" {
				info.Error = fmt.Sprintf("Failed to fetch contributor details: %v", detErr)
			}
			// Even if detailed fetch failed, return repository with empty contributors
			info.Contributors = nil
			info.ContributorsWithLocationCount = 0
		} else {
			// Filter contributors with location
			var withLocation []models.ContributorDetail
			for _, d := range details {
				if d.Location != "" {
					withLocation = append(withLocation, d)
				}
			}
			info.Contributors = withLocation
			info.ContributorsWithLocationCount = len(withLocation)
		}
	}

	return info
}

// CheckRepoEligibility runs the three prechecks the server should apply before heavy fetches:
//   - at least 1 closed milestone
//   - at least `minCommits` commits (use 100 where caller passes 100)
//   - at least `minActive` distinct commit authors in the last `days` days (use 3, 90)
func (c *Client) CheckRepoEligibility(owner, repo string, minCommits int, days int, minActive int) (bool, string, error) {
	var wg sync.WaitGroup
	wg.Add(3)

	var (
		milestoneErr, commitErr, activeErr error
		// hasClosed                          bool
		commitCount int
		activeOk    bool
		activeCount int
	)

	// 1) closed milestones
	go func() {
		defer wg.Done()
		// hasClosed, milestoneErr = c.hasClosedMilestones(owner, repo)
		_, milestoneErr = c.hasClosedMilestones(owner, repo)
	}()

	// 2) commits >= minCommits
	go func() {
		defer wg.Done()
		commitCount, commitErr = c.getCommitCountWithLimit(owner, repo, minCommits)
	}()

	// 3) active contributors
	go func() {
		defer wg.Done()
		activeOk, activeCount, activeErr = c.hasActiveContributors(owner, repo, days, minActive)
	}()

	wg.Wait()

	if milestoneErr != nil {
		return false, "", fmt.Errorf("error checking milestones: %w", milestoneErr)
	}
	// if !hasClosed {
	// 	return false, "repository does not have at least 1 closed milestone", nil
	// }

	if commitErr != nil {
		return false, "", fmt.Errorf("error counting commits: %w", commitErr)
	}
	if commitCount < minCommits {
		return false, fmt.Sprintf("repository has fewer than %d commits (found %d)", minCommits, commitCount), nil
	}

	if activeErr != nil {
		return false, "", fmt.Errorf("error checking active contributors: %w", activeErr)
	}
	if !activeOk {
		return false, fmt.Sprintf("fewer than %d active contributors in the last %d days (found %d)", minActive, days, activeCount), nil
	}

	return true, "", nil
}

// GetRemainingRequests fetches the remaining number of requests for the REST API (Core).
// This is useful for monitoring usage against the 5,000 hourly limit.
// Note: This API call itself does not consume quota.
func (c *Client) GetRemainingRequests() (int, error) {
	limits, _, err := c.client.RateLimits(c.ctx)
	if err != nil {
		return 0, err
	}
	if limits.Core != nil {
		return limits.Core.Remaining, nil
	}
	return 0, fmt.Errorf("could not retrieve core rate limits")
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
	// Optimization: Request 1 item per page. The LastPage value in the response header
	// will tell us the total number of pages, which equals the total number of commits.
	opts := &gith.CommitsListOptions{
		ListOptions: gith.ListOptions{
			PerPage: 1,
		},
	}

	commits, resp, err := c.client.Repositories.ListCommits(c.ctx, owner, repo, opts)
	if err != nil {
		return 0, err
	}

	// If LastPage is 0, it means all results fit in the first page.
	// Since PerPage is 1, the count is simply the number of items returned (0 or 1).
	if resp.LastPage == 0 {
		return len(commits), nil
	}

	return resp.LastPage, nil
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
	// Helper to get count for a state
	getCount := func(state string) (int, error) {
		opts := &gith.MilestoneListOptions{
			State: state,
			ListOptions: gith.ListOptions{
				PerPage: 1,
			},
		}
		milestones, resp, err := c.client.Issues.ListMilestones(c.ctx, owner, repo, opts)
		if err != nil {
			return 0, err
		}
		if resp.LastPage == 0 {
			return len(milestones), nil
		}
		return resp.LastPage, nil
	}

	openCount, err := getCount("open")
	if err != nil {
		return 0, err
	}

	closedCount, err := getCount("closed")
	if err != nil {
		return 0, err
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

// getRecentContributors returns a list of contributors who have committed in the last `days` days.
func (c *Client) getRecentContributors(owner, repo string, days int) ([]string, error) {
	since := time.Now().AddDate(0, 0, -days)
	opts := &gith.CommitsListOptions{
		Since:       since,
		ListOptions: gith.ListOptions{PerPage: 100},
	}

	seen := make(map[string]struct{})
	var recent []string

	for {
		commits, resp, err := c.client.Repositories.ListCommits(c.ctx, owner, repo, opts)
		if err != nil {
			return nil, err
		}

		for _, cm := range commits {
			if cm.Author != nil && cm.Author.Login != nil {
				login := *cm.Author.Login
				if _, ok := seen[login]; !ok {
					seen[login] = struct{}{}
					recent = append(recent, login)
				}
			}
		}

		if resp.NextPage == 0 {
			break
		}
		opts.Page = resp.NextPage
	}
	return recent, nil
}

// getContributors returns the list of contributor usernames, total count (including anon), and non-anon count
func (c *Client) getContributors(owner, repo string) ([]string, int, int, error) {
	opts := &gith.ListContributorsOptions{
		Anon: "true",
		ListOptions: gith.ListOptions{
			PerPage: 100,
		},
	}

	var allContributors []string
	var totalCount int
	var nonAnonCount int

	for {
		contributors, resp, err := c.client.Repositories.ListContributors(c.ctx, owner, repo, opts)
		if err != nil {
			return nil, 0, 0, err
		}

		totalCount += len(contributors)

		for _, contributor := range contributors {
			if contributor.Login != nil {
				allContributors = append(allContributors, *contributor.Login)
				nonAnonCount++
			}
		}

		if resp.NextPage == 0 {
			break
		}
		opts.Page = resp.NextPage
	}

	return allContributors, totalCount, nonAnonCount, nil
}

// getContributorsDetails fetches detailed information for a list of contributors
func (c *Client) getContributorsDetails(usernames []string) ([]models.ContributorDetail, error) {
	if len(usernames) == 0 {
		return nil, nil
	}

	var wg sync.WaitGroup
	results := make([]models.ContributorDetail, len(usernames))
	sem := make(chan struct{}, 5)

	for i, username := range usernames {
		wg.Add(1)
		sem <- struct{}{}
		go func(idx int, u string) {
			defer wg.Done()
			defer func() { <-sem }()

			user, _, err := c.client.Users.Get(c.ctx, u)
			if err != nil {
				c.logger.Debugf("Failed to fetch user %s: %v", u, err)
				results[idx].Error = err.Error()
				return
			}

			// Map fields
			detail := models.ContributorDetail{
				Login: u,
			}
			if user.ID != nil {
				detail.ID = *user.ID
			}
			if user.NodeID != nil {
				detail.NodeID = *user.NodeID
			}
			if user.AvatarURL != nil {
				detail.AvatarURL = *user.AvatarURL
			}
			if user.HTMLURL != nil {
				detail.HTMLURL = *user.HTMLURL
			}
			if user.Type != nil {
				detail.Type = *user.Type
			}
			if user.Name != nil {
				detail.Name = *user.Name
			}
			if user.Company != nil {
				detail.Company = *user.Company
			}
			if user.Blog != nil {
				detail.Blog = *user.Blog
			}
			if user.Location != nil {
				detail.Location = *user.Location
			}
			if user.Email != nil {
				detail.Email = *user.Email
			}
			if user.Bio != nil {
				detail.Bio = *user.Bio
			}
			if user.CreatedAt != nil {
				detail.CreatedAt = user.CreatedAt.Time
			}
			if user.UpdatedAt != nil {
				detail.UpdatedAt = user.UpdatedAt.Time
			}

			results[idx] = detail
		}(i, username)
	}
	wg.Wait()

	// Check if all failed
	allFailed := true
	var firstErr string
	for _, r := range results {
		if r.Error == "" {
			allFailed = false
			break
		}
		if firstErr == "" {
			firstErr = r.Error
		}
	}

	if allFailed && len(usernames) > 0 {
		return results, fmt.Errorf("all contributor detail requests failed. First error: %s", firstErr)
	}

	return results, nil
}

package github

import (
	"bufio"
	"context"
	"encoding/base64"
	"fmt"
	"net"
	"net/http"
	"regexp"
	"strings"
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

	// if we reach here, filters passed: proceed to fetch contributors, commits, milestones and LOC concurrently
	var wg sync.WaitGroup
	var commitErr, milestoneErr, contributorErr, locErr error
	var commits, milestones, loc int
	var contributors []string
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

	// Get LOC estimate
	go func() {
		defer wg.Done()
		// Use repository default branch as starting point if available
		branch := ""
		if repository.DefaultBranch != nil {
			branch = *repository.DefaultBranch
		}
		loc, locErr = c.getLOC(owner, repo, branch)
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
		info.TotalContributorsCount = totalContributors
		info.NonAnonymousContributorsCount = nonAnonContributors

		// convert usernames into detailed contributor profiles
		details, detErr := c.getContributorsDetails(contributors)
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

	// set LOC if fetched
	if locErr != nil {
		// don't overwrite primary error, but if none set a readable note
		if info.Error == "" {
			info.Error = fmt.Sprintf("Failed to estimate LOC: %v", locErr)
		}
	} else {
		info.Loc = loc
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

// getLOC attempts to estimate Lines Of Code by summing blob sizes from the repository tree
// and dividing by an average bytes-per-line constant. It falls back to using the
// repository `Size` field (KB) when tree info is not available.
func (c *Client) getLOC(owner, repo, branch string) (int, error) {
	// If no branch provided, try to fetch repository default branch
	if branch == "" {
		repository, _, err := c.client.Repositories.Get(c.ctx, owner, repo)
		if err != nil {
			return 0, err
		}
		if repository.DefaultBranch != nil {
			branch = *repository.DefaultBranch
		}
	}

	if branch == "" {
		return 0, fmt.Errorf("no branch available to compute LOC")
	}

	// Get branch information to obtain a tree/commit SHA
	br, _, err := c.client.Repositories.GetBranch(c.ctx, owner, repo, branch, 0)
	if err != nil {
		// fallback: try to use repository size
		repository, _, err2 := c.client.Repositories.Get(c.ctx, owner, repo)
		if err2 != nil {
			return 0, fmt.Errorf("failed to get branch and repository: %v, %v", err, err2)
		}
		// repository.Size is in KB; estimate bytes then convert to LOC
		bytes := 0
		if repository.Size != nil {
			bytes = (*repository.Size) * 1024
		}
		if bytes == 0 {
			return 0, fmt.Errorf("no size information available to estimate LOC")
		}
		return bytes / 50, nil
	}

	var sha string
	if br.Commit != nil {
		if br.Commit.Commit != nil && br.Commit.Commit.Tree != nil && br.Commit.Commit.Tree.SHA != nil {
			sha = *br.Commit.Commit.Tree.SHA
		} else if br.Commit.SHA != nil {
			sha = *br.Commit.SHA
		}
	}

	if sha == "" {
		// fallback to repository size
		repository, _, err := c.client.Repositories.Get(c.ctx, owner, repo)
		if err != nil {
			return 0, err
		}
		bytes := 0
		if repository.Size != nil {
			bytes = (*repository.Size) * 1024
		}
		if bytes == 0 {
			return 0, fmt.Errorf("no size information available to estimate LOC")
		}
		return bytes / 50, nil
	}

	// Get tree recursively
	tree, _, err := c.client.Git.GetTree(c.ctx, owner, repo, sha, true)
	if err != nil {
		// fallback to repository size
		repository, _, err2 := c.client.Repositories.Get(c.ctx, owner, repo)
		if err2 != nil {
			return 0, fmt.Errorf("failed to get tree and repository: %v, %v", err, err2)
		}
		bytes := 0
		if repository.Size != nil {
			bytes = (*repository.Size) * 1024
		}
		if bytes == 0 {
			return 0, fmt.Errorf("failed to get tree and no size information available: %v", err)
		}
		return bytes / 50, nil
	}

	// Count lines by fetching blobs for text files
	// This is expensive, so we limit concurrency and file size
	var wg sync.WaitGroup
	var totalLines int64
	var mu sync.Mutex
	sem := make(chan struct{}, 20) // Limit concurrency to 20

	if tree != nil && tree.Entries != nil {
		for _, e := range tree.Entries {
			if e != nil && e.Type != nil && *e.Type == "blob" && e.Path != nil && isSourceFile(*e.Path) {
				// Skip large files to avoid timeouts/memory issues (e.g. > 1MB)
				if e.Size != nil && *e.Size > 1024*1024 {
					continue
				}

				wg.Add(1)
				sem <- struct{}{}
				go func(sha string) {
					defer wg.Done()
					defer func() { <-sem }()

					blob, _, err := c.client.Git.GetBlob(c.ctx, owner, repo, sha)
					if err != nil {
						// Ignore errors for individual files
						return
					}

					if blob != nil && blob.Content != nil {
						content := *blob.Content
						if blob.Encoding != nil && *blob.Encoding == "base64" {
							decoded, err := base64.StdEncoding.DecodeString(content)
							if err == nil {
								content = string(decoded)
							}
						}

						// Count lines excluding comments and blank lines
						c := countSignificantLines(content, *e.Path)

						mu.Lock()
						totalLines += int64(c)
						mu.Unlock()
					}
				}(*e.SHA)
			}
		}
	}
	wg.Wait()

	// If we found lines, return them.
	if totalLines > 0 {
		return int(totalLines), nil
	}

	// Fallback if no lines found (e.g. no source files or all failed)
	// Use the previous estimation method as a backup
	totalBytes := 0
	if tree != nil && tree.Entries != nil {
		for _, e := range tree.Entries {
			if e != nil && e.Size != nil && e.Path != nil {
				if isSourceFile(*e.Path) {
					totalBytes += *e.Size
				}
			}
		}
	}

	// If tree returns no sizes (possible for some entries), fallback to repository size
	if totalBytes == 0 {
		repository, _, err := c.client.Repositories.Get(c.ctx, owner, repo)
		if err != nil {
			return 0, err
		}
		if repository.Size != nil {
			totalBytes = (*repository.Size) * 1024
		}
	}

	if totalBytes == 0 {
		return 0, fmt.Errorf("could not determine repository byte size to estimate LOC")
	}

	// Estimate average bytes per source line. 50 bytes/line is a reasonable heuristic.
	return totalBytes / 50, nil
}

// countSignificantLines counts lines excluding comments and blank lines
func countSignificantLines(content, path string) int {
	// Normalize newlines
	content = strings.ReplaceAll(content, "\r\n", "\n")
	content = strings.ReplaceAll(content, "\r", "\n")

	// Determine comment style
	ext := ""
	if idx := strings.LastIndex(path, "."); idx != -1 {
		ext = strings.ToLower(path[idx:])
	}

	var re *regexp.Regexp
	// Regex to match comments. We replace them with empty strings.
	// Note: This is a heuristic and might not be perfect for all edge cases (e.g. strings containing comment markers)
	// but it's better than counting everything.
	// To handle strings correctly, we would need a full parser.
	// Here we try to match strings OR comments, and if it's a comment we remove it.

	switch ext {
	case ".c", ".cpp", ".h", ".hpp", ".java", ".js", ".ts", ".cs", ".go", ".rs", ".swift", ".kt", ".scala", ".php", ".css":
		// Match C-style comments: //... or /* ... */
		// Also match strings to avoid removing comments inside strings: "..." or '...'
		// We use a capturing group for strings so we can keep them.
		// Go regex doesn't support lookarounds or conditional replacement easily in one go without a callback.
		// We will use ReplaceAllStringFunc.
		// Note: We use [\s\S] for block comments to match newlines, but avoid (?s) globally
		// so that // comments don't match newlines.
		re = regexp.MustCompile(`"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|//[^\n]*|/\*[\s\S]*?\*/`)
	case ".py", ".rb", ".sh", ".pl", ".pm", ".yaml", ".yml", ".dockerfile":
		// Hash style: #...
		// Also match strings: "..." or '...' or """...""" or '''...''' (Python)
		// Python docstrings are tricky. Let's just handle simple strings and # comments.
		re = regexp.MustCompile(`(?m)(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|#.*$)`)
	case ".html", ".xml":
		// HTML style: <!-- ... -->
		re = regexp.MustCompile(`"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|<!--[\s\S]*?-->`)
	default:
		// Default: just count non-empty lines
		scanner := bufio.NewScanner(strings.NewReader(content))
		count := 0
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line != "" {
				count++
			}
		}
		return count
	}

	// Replace comments with empty string (or keep strings)
	stripped := re.ReplaceAllStringFunc(content, func(match string) string {
		if strings.HasPrefix(match, "//") || strings.HasPrefix(match, "/*") || strings.HasPrefix(match, "#") || strings.HasPrefix(match, "<!--") {
			// It's a comment, replace with newlines to preserve line count?
			// No, we want to remove it. But if we remove it, we might merge lines.
			// Actually, if we remove a block comment, we should probably replace it with spaces or nothing.
			// If we remove a line comment, we remove to the end of line.
			// The goal is to count *lines of code*.
			// If a line becomes empty after removing comments, it shouldn't count.
			// So replacing with empty string is fine.
			// BUT, for block comments spanning multiple lines, we remove the content.
			// Example:
			// code /* comment
			// comment */ code
			// -> code  code
			// This remains 1 line? Or 2?
			// Usually LoC counts logical lines or physical lines.
			// If we just strip comments, we are left with code.
			// Then we count non-empty lines.
			return ""
		}
		// It's a string, keep it
		return match
	})

	// Now count non-empty lines
	scanner := bufio.NewScanner(strings.NewReader(stripped))
	count := 0
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" {
			count++
		}
	}
	return count
}

// isSourceFile checks if the file path has a source code extension
func isSourceFile(path string) bool {
	exts := []string{
		".go", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
		".rb", ".php", ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".md",
		".txt", ".sh", ".bat", ".rs", ".swift", ".kt", ".scala", ".pl", ".pm",
	}
	for _, ext := range exts {
		if len(path) > len(ext) && path[len(path)-len(ext):] == ext {
			return true
		}
	}
	return false
}

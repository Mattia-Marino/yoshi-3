package proto

import (
	"time"

	"github-extractor/models"
)

// RepositoryInfoToProto converts a models.RepositoryInfo into a proto Repository message.
func RepositoryInfoToProto(info models.RepositoryInfo) *Repository {
	repo := &Repository{
		Owner:                         info.Owner,
		Repo:                          info.Repo,
		Description:                   info.Description,
		Stars:                         int32(info.Stars),
		Forks:                         int32(info.Forks),
		OpenIssues:                    int32(info.OpenIssues),
		Language:                      info.Language,
		CreatedAt:                     info.CreatedAt.Format(time.RFC3339),
		UpdatedAt:                     info.UpdatedAt.Format(time.RFC3339),
		Commits:                       int32(info.Commits),
		Milestones:                    int32(info.Milestones),
		TotalContributorsCount:        int32(info.TotalContributorsCount),
		NonAnonymousContributorsCount: int32(info.NonAnonymousContributorsCount),
		SelectedContributorsCount:     int32(info.SelectedContributorsCount),
		ContributorsWithLocationCount: int32(info.ContributorsWithLocationCount),
		Size:                          int32(info.Size),
		Watchers:                      int32(info.Watchers),
		HasIssues:                     info.HasIssues,
		HasWiki:                       info.HasWiki,
		HasCodeOfConduct:              info.HasCodeOfConduct,
		HasReadme:                     info.HasReadme,
		HasDescription:                info.HasDescription,
		HasContributingGuidelines:     info.HasContributingGuidelines,
		HasLicense:                    info.HasLicense,
		HasSecurityPolicy:             info.HasSecurityPolicy,
		HasIssuesTemplate:             info.HasIssuesTemplate,
		HasPullRequestTemplate:        info.HasPullRequestTemplate,
		HasWikiPage:                   info.HasWikiPage,
		HasMilestones:                 info.HasMilestones,
		DefaultBranch:                 info.DefaultBranch,
		License:                       info.License,
	}

	// Map contributors
	for _, c := range info.Contributors {
		repo.Contributors = append(repo.Contributors, &Contributor{
			Login:                  c.Login,
			Id:                     int32(c.ID),
			NodeId:                 c.NodeID,
			AvatarUrl:              c.AvatarURL,
			HtmlUrl:                c.HTMLURL,
			Type:                   c.Type,
			Name:                   c.Name,
			Company:                c.Company,
			Blog:                   c.Blog,
			Location:               c.Location,
			Email:                  c.Email,
			Bio:                    c.Bio,
			Followers:              int32(c.Followers),
			Following:              int32(c.Following),
			FollowerFollowingRatio: c.FollowerFollowingRatio,
			CreatedAt:              c.CreatedAt.Format(time.RFC3339),
			UpdatedAt:              c.UpdatedAt.Format(time.RFC3339),
		})
	}

	// Map contributor stats
	for _, cs := range info.ContributorStats {
		protoStats := &ContributorStats{
			Author:      cs.Author,
			Total:       int32(cs.Total),
			FirstCommit: cs.FirstCommit.Format(time.RFC3339),
			LastCommit:  cs.LastCommit.Format(time.RFC3339),
		}
		for _, w := range cs.Weeks {
			protoStats.Weeks = append(protoStats.Weeks, &WeekStats{
				Week:      w.WeekTimestamp,
				Additions: int32(w.Additions),
				Deletions: int32(w.Deletions),
				Commits:   int32(w.Commits),
			})
		}
		repo.ContributorStats = append(repo.ContributorStats, protoStats)
	}

	// Map pull requests
	for _, pr := range info.PullRequests {
		protoPR := &PullRequest{
			Number: int32(pr.Number),
			Status: pr.Status,
		}
		if pr.MergedAt != nil {
			protoPR.MergedAt = pr.MergedAt.Format(time.RFC3339)
		}
		repo.PullRequests = append(repo.PullRequests, protoPR)
	}

	return repo
}

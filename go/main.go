package main

import (
	"fmt"
	"log"
	"path/filepath"
	"strings"

	"github-extractor/config"
	csvpkg "github-extractor/csv"
	"github-extractor/github"
	"github-extractor/models"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Configuration error: %v", err)
	}

	// Determine the correct path to input.csv (parent directory)
	inputPath := filepath.Join("..", cfg.InputFile)
	outputPath := filepath.Join("..", cfg.OutputFile)

	// Read input CSV
	reader := csvpkg.NewReader(inputPath)
	repositories, err := reader.ReadRepositories()
	if err != nil {
		log.Fatalf("Failed to read input CSV: %v", err)
	}

	fmt.Printf("Found %d repositories to process\n\n", len(repositories))

	// Create GitHub client
	ghClient := github.NewClient(cfg.GitHubToken)

	// Fetch information for each repository
	results := make([]models.RepositoryInfo, 0, len(repositories))
	for i, repo := range repositories {
		fmt.Printf("[%d/%d] Fetching information for %s/%s...\n", i+1, len(repositories), repo.Owner, repo.Repo)

		info := ghClient.GetRepositoryInfo(repo.Owner, repo.Repo)
		results = append(results, info)

		// Print information to screen
		printRepositoryInfo(info)
		fmt.Println(strings.Repeat("-", 80))
	}

	// Write results to output CSV
	writer := csvpkg.NewWriter(outputPath)
	if err := writer.WriteRepositories(results); err != nil {
		log.Fatalf("Failed to write output CSV: %v", err)
	}

	fmt.Printf("\n✓ Successfully processed %d repositories\n", len(repositories))
	fmt.Printf("✓ Output written to %s\n", outputPath)
}

// printRepositoryInfo prints repository information to screen
func printRepositoryInfo(info models.RepositoryInfo) {
	if info.Error != "" {
		fmt.Printf("  ERROR: %s\n", info.Error)
		return
	}

	fmt.Printf("  Repository: %s/%s\n", info.Owner, info.Repo)
	fmt.Printf("  Description: %s\n", truncate(info.Description, 80))
	fmt.Printf("  Language: %s\n", info.Language)
	fmt.Printf("  Stars: %d | Forks: %d | Watchers: %d\n", info.Stars, info.Forks, info.Watchers)
	fmt.Printf("  Open Issues: %d\n", info.OpenIssues)
	fmt.Printf("  Commits: %d | Milestones: %d\n", info.Commits, info.Milestones)
	fmt.Printf("  Size: %d KB\n", info.Size)
	fmt.Printf("  License: %s\n", info.License)
	fmt.Printf("  Created: %s | Updated: %s\n",
		info.CreatedAt.Format("2006-01-02"),
		info.UpdatedAt.Format("2006-01-02"))
	fmt.Printf("  Default Branch: %s\n", info.DefaultBranch)
	fmt.Printf("  Has Issues: %t | Has Wiki: %t\n", info.HasIssues, info.HasWiki)
}

// truncate truncates a string to maxLen characters
func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}

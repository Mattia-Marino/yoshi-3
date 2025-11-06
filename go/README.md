# GitHub Repository Data Extractor

A modular Go program that extracts detailed information from GitHub repositories, including commit counts and milestones.

## Features

- Reads repository list from CSV file
- Fetches comprehensive repository information using GitHub API
- Retrieves commit counts and milestone data
- Outputs results to both console and CSV file
- Modular architecture for easy maintenance and testing

## Prerequisites

- Go 1.21 or higher
- GitHub Personal Access Token

## Setup

1. **Get a GitHub Personal Access Token:**
   - Go to GitHub Settings → Developer settings → Personal access tokens
   - Generate a new token with `repo` and `public_repo` permissions
   - Copy the token

2. **Set the environment variable:**
   ```bash
   export YOSHI-GH-TOKEN="your_github_token_here"
   ```

3. **Install dependencies:**
   ```bash
   cd go
   go mod download
   ```

## Project Structure

```
go/
├── main.go              # Entry point
├── config/
│   └── config.go        # Configuration management
├── models/
│   └── repository.go    # Data models
├── github/
│   └── client.go        # GitHub API client
├── csv/
│   ├── reader.go        # CSV input reading
│   └── writer.go        # CSV output writing
└── go.mod               # Go module definition
```

## Usage

1. **Prepare input file:**
   Create `input.csv` in the project root with the following format:
   ```csv
   owner,repo
   tensorflow,tensorflow
   microsoft,vscode
   ```

2. **Run the program:**
   ```bash
   cd go
   go run main.go
   ```

   Or build and run:
   ```bash
   cd go
   go build -o github-extractor
   ./github-extractor
   ```

3. **Output:**
   - Console: Displays detailed information for each repository
   - File: Creates `output.csv` in the project root with all extracted data

## Output CSV Fields

The program extracts the following information for each repository:

- **Owner**: Repository owner
- **Repo**: Repository name
- **Description**: Repository description
- **Stars**: Number of stars
- **Forks**: Number of forks
- **OpenIssues**: Number of open issues
- **Language**: Primary programming language
- **CreatedAt**: Creation date
- **UpdatedAt**: Last update date
- **Commits**: Total number of commits
- **Milestones**: Total number of milestones (open + closed)
- **Size**: Repository size in KB
- **Watchers**: Number of watchers
- **HasIssues**: Whether issues are enabled
- **HasWiki**: Whether wiki is enabled
- **DefaultBranch**: Default branch name
- **License**: License type
- **Error**: Any errors encountered during fetching

## Error Handling

- If the `YOSHI-GH-TOKEN` environment variable is not set, the program will exit with an error
- If a repository cannot be accessed, the error will be logged in the output CSV
- Network errors and API rate limits are handled gracefully

## Notes

- The program respects GitHub API rate limits
- Large repositories with many commits may take longer to process
- Make sure your token has sufficient permissions to access the repositories

## Example

```bash
# Set token
export YOSHI-GH-TOKEN="ghp_your_token_here"

# Run program
cd go
go run main.go

# Output
Found 15 repositories to process

[1/15] Fetching information for tensorflow/tensorflow...
  Repository: tensorflow/tensorflow
  Description: An Open Source Machine Learning Framework for Everyone
  Language: C++
  Stars: 180000 | Forks: 74000 | Watchers: 9000
  Open Issues: 2000
  Commits: 50000 | Milestones: 45
  ...
--------------------------------------------------------------------------------
...

✓ Successfully processed 15 repositories
✓ Output written to ../output.csv
```

# Quick Reference

## Setup (One-time)

```bash
# Get GitHub token from https://github.com/settings/tokens
# Required permissions: repo, public_repo

export YOSHI-GH-TOKEN="ghp_your_token_here"
```

## Run

```bash
# Option 1: Use the provided script
./run.sh

# Option 2: Manual execution
cd go
go run main.go

# Option 3: Build binary first
cd go
go build -o github-extractor
./github-extractor
```

## Input Format

**input.csv** (in project root):
```csv
owner,repo
tensorflow,tensorflow
microsoft,vscode
golang,go
```

## Output

**Console**: Live progress and details
```
Found 3 repositories to process

[1/3] Fetching information for tensorflow/tensorflow...
  Repository: tensorflow/tensorflow
  Description: An Open Source Machine Learning Framework...
  Stars: 180000 | Forks: 74000 | Watchers: 9000
  Commits: 50000 | Milestones: 45
  ...
```

**output.csv** (in project root): Complete data with 18 fields

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `YOSHI-GH-TOKEN is not set` | Export the environment variable |
| `Failed to open input.csv` | Ensure input.csv exists in project root |
| `Failed to fetch repository` | Check repository exists and token has access |
| `API rate limit` | Wait 1 hour or use different token |

## Key Features

- ✅ Fetches 18 data points per repository
- ✅ Counts total commits (including all branches)
- ✅ Counts total milestones (open + closed)
- ✅ Handles errors gracefully
- ✅ Processes multiple repositories sequentially
- ✅ Outputs to both console and CSV

## Project Structure

```
.
├── input.csv              # INPUT: Repository list
├── output.csv             # OUTPUT: Extracted data
├── run.sh                 # Convenience script
├── README.md              # Main documentation
├── IMPLEMENTATION.md      # Technical details
└── go/                    # Go application
    ├── main.go
    ├── config/
    ├── models/
    ├── github/
    └── csv/
```

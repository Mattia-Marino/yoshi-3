# YOSHI-3

Reimplementation of YOSHI for the course of Software Evolution and Quality at University of Sannio by prof. Damian A. Tamburri.

## Overview

This project contains a modular Go program that extracts detailed information from GitHub repositories. The program reads a list of repositories from `input.csv`, fetches data using the GitHub API, and outputs the results to both the console and `output.csv`.

## Quick Start

1. **Set up your GitHub token:**
   ```bash
   export YOSHI-GH-TOKEN="your_github_token_here"
   ```

2. **Run the program:**
   ```bash
   cd go
   go run main.go
   ```

3. **Check the output:**
   - Console output shows progress and details for each repository
   - `output.csv` contains all extracted data in CSV format

## Features

- ✅ Modular Go architecture with separate packages for each concern
- ✅ Fetches comprehensive repository information from GitHub API
- ✅ Retrieves commit counts and milestone data
- ✅ Error handling with detailed error messages
- ✅ CSV input/output support
- ✅ Environment variable configuration

## Project Structure

```
├── input.csv           # Input file with owner,repo list
├── output.csv          # Generated output with repository data
├── README.md           # This file
└── go/                 # Go application
    ├── main.go         # Entry point
    ├── config/         # Configuration management
    ├── models/         # Data models
    ├── github/         # GitHub API client
    ├── csv/            # CSV reader and writer
    └── README.md       # Detailed Go documentation
```

## Documentation

For detailed documentation about the Go program, see [go/README.md](go/README.md).

## Requirements

- Go 1.21 or higher
- GitHub Personal Access Token with `repo` permissions
- Input CSV file with `owner` and `repo` columns

## Output Data

The program extracts the following information for each repository:
- Basic info: owner, name, description, language
- Metrics: stars, forks, watchers, open issues, size
- **Commits**: Total number of commits
- **Milestones**: Total number of milestones (open + closed)
- Metadata: creation date, last update, default branch, license
- Flags: has issues, has wiki

## Error Handling

- Missing `YOSHI-GH-TOKEN` environment variable → Program exits with error
- Invalid or inaccessible repositories → Error logged in output CSV
- Network issues → Gracefully handled with error messages

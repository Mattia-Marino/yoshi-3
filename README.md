# YOSHI-3

Reimplementation of YOSHI for the course of Software Evolution and Quality at University of Sannio by prof. Damian A. Tamburri.

## Overview

A high-performance HTTP server written in Go that extracts comprehensive information from GitHub repositories using full CPU parallelization. The server accepts GET requests with JSON payloads and returns detailed repository data including commits, milestones, and contributors.

## Key Features

- 🚀 **Full Parallelization**: One repository per CPU core for maximum throughput
- 🌐 **HTTP API**: RESTful server with JSON input/output
- 📊 **Comprehensive Data**: Repository info, commits, milestones, and contributors
- ⚡ **High Performance**: Worker pool pattern with concurrent API calls
- 🔧 **Modular Architecture**: Clean separation of concerns

## Quick Start

1. **Set up your GitHub token:**
   ```bash
   export YOSHI_GH_TOKEN="your_github_token_here"
   ```

2. **Start the server:**
   ```bash
   cd go
   go build -o github-extractor
   ./github-extractor
   ```

3. **Make a request:**
   ```bash
   curl -X GET http://localhost:8080/extract \
     -H "Content-Type: application/json" \
     -d '{"input_file_path": "/absolute/path/to/input.csv"}'
   ```

## API Endpoints

### Health Check
```
GET /health
```
Returns server status and number of CPU cores being used.

### Extract Repository Data
```
GET /extract
Content-Type: application/json

{
  "input_file_path": "/absolute/path/to/input.csv"
}
```

Returns JSON with all repository information:
```json
{
  "repositories": [
    {
      "owner": "tensorflow",
      "repo": "tensorflow",
      "stars": 180000,
      "commits": 50000,
      "milestones": 45,
      "contributors": ["user1", "user2", ...],
      ...
    }
  ],
  "total_count": 1
}
```

## Architecture

```
Client Request
      ↓
HTTP Server (port 8080)
      ↓
Worker Pool (N cores)
      ↓
GitHub API (parallel)
      ↓
JSON Response
```

### Parallelization Model

- **Worker Pool**: Creates N workers where N = number of CPU cores
- **Job Distribution**: Repositories are distributed across workers via channels
- **Concurrent Execution**: Each worker processes repositories independently
- **Result Collection**: All results are aggregated and returned as single JSON

## Input Format

**input.csv** (requires absolute path):
```csv
owner,repo
tensorflow,tensorflow
microsoft,vscode
golang,go
```

## Output Data

Each repository JSON object contains 19 fields:

| Category | Fields |
|----------|--------|
| **Identity** | owner, repo, description |
| **Metrics** | stars, forks, watchers, open_issues, size |
| **Activity** | commits, milestones, contributors |
| **Metadata** | language, created_at, updated_at, default_branch, license |
| **Features** | has_issues, has_wiki |
| **Errors** | error (if any) |

## Performance

- **Concurrency**: Utilizes all CPU cores (GOMAXPROCS set to NumCPU)
- **Scalability**: Linear scaling with number of cores
- **Efficiency**: Non-blocking I/O with goroutines
- **Resource Management**: Bounded worker pool prevents resource exhaustion

### Example Benchmarks
- 15 repositories on 8-core machine: ~30-60 seconds
- Processing time depends on largest repository size
- GitHub API rate limit: 5,000 requests/hour (authenticated)

## Project Structure

```
.
├── input.csv              # Sample input
├── test-server.sh         # Testing script
├── README.md              # This file
└── go/                    # Go application
    ├── main.go            # Server entry point
    ├── config/            # Configuration
    ├── models/            # Data structures
    ├── github/            # GitHub API client
    ├── csv/               # CSV reader
    └── server/            # HTTP handlers & workers
```

## Testing

Use the provided test script:
```bash
./test-server.sh
```

This will:
1. Start the server
2. Test health endpoint
3. Make a request with input.csv
4. Save response to output.json
5. Display summary
6. Stop the server

## Documentation

- **README.md**: Main project overview (this file)
- **go/README.md**: Detailed API and implementation docs
- **IMPLEMENTATION.md**: Technical implementation details (legacy)

## Requirements

- Go 1.21 or higher
- GitHub Personal Access Token with `repo` permissions
- Linux/macOS/Windows with bash (for test script)

## Error Handling

| Error | HTTP Status | Response |
|-------|-------------|----------|
| Missing token | N/A | Server won't start |
| Invalid JSON | 400 | `{"error": "Invalid JSON: ..."}` |
| Missing input_file_path | 400 | `{"error": "input_file_path is required"}` |
| Invalid CSV file | 400 | `{"error": "Failed to read input file: ..."}` |
| Repository errors | 200 | Logged in repository object's `error` field |

## Environment Variables

- `YOSHI_GH_TOKEN` (required): GitHub Personal Access Token
- `PORT` (optional): Server port (default: 8080)

## Differences from Previous Version

### Before (CLI Tool)
- Sequential processing
- CSV output only
- Console logging
- No parallelization

### Now (HTTP Server)
- Full parallelization (one repo per core)
- JSON API
- RESTful architecture
- Worker pool pattern
- Contributor data included

## License

Academic project for Software Evolution and Quality course.

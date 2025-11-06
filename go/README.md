# GitHub Repository Data Extractor - HTTP Server

A highly concurrent Go server that extracts detailed information from GitHub repositories using full CPU parallelization.

## Features

- **HTTP API**: RESTful server accepting GET requests with JSON payloads
- **Full Parallelization**: One repository per CPU core for maximum performance
- **Comprehensive Data**: Fetches repository info, commits, milestones, and contributors
- **JSON Output**: Returns structured JSON for each repository
- **Worker Pool**: Efficient concurrent processing using Go routines

## Architecture

The server uses a worker pool pattern with one worker per CPU core:
- Jobs are distributed across all available cores
- Each worker processes repositories independently
- Results are collected and returned as a single JSON response

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
   export YOSHI_GH_TOKEN="your_github_token_here"
   ```

3. **Build the server:**
   ```bash
   cd go
   go build -o github-extractor
   ```

## Usage

### Start the Server

```bash
cd go
./github-extractor
```

The server will start on port 8080 (configurable via `PORT` environment variable).

### API Endpoints

#### Health Check
```bash
GET /health
```

Response:
```json
{
  "status": "ok",
  "cores": 8
}
```

#### Extract Repository Data
```bash
GET /extract
Content-Type: application/json

{
  "input_file_path": "/absolute/path/to/input.csv"
}
```

**Request Parameters:**
- `input_file_path` (string, required): Absolute path to the input CSV file

**Response:**
```json
{
  "repositories": [
    {
      "owner": "tensorflow",
      "repo": "tensorflow",
      "description": "An Open Source Machine Learning Framework...",
      "stars": 180000,
      "forks": 74000,
      "open_issues": 2000,
      "language": "C++",
      "created_at": "2015-11-07T01:19:20Z",
      "updated_at": "2024-11-06T10:30:15Z",
      "commits": 50000,
      "milestones": 45,
      "contributors": ["user1", "user2", "user3", ...],
      "size": 250000,
      "watchers": 9000,
      "has_issues": true,
      "has_wiki": true,
      "default_branch": "main",
      "license": "Apache License 2.0"
    }
  ],
  "total_count": 1
}
```

### Example Request

```bash
curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d '{"input_file_path": "/home/user/input.csv"}'
```

## Input CSV Format

The input CSV file must have the following format:

```csv
owner,repo
tensorflow,tensorflow
microsoft,vscode
golang,go
```

## Output Data Fields

Each repository object in the JSON response contains:

| Field | Type | Description |
|-------|------|-------------|
| `owner` | string | Repository owner |
| `repo` | string | Repository name |
| `description` | string | Repository description |
| `stars` | int | Number of stars |
| `forks` | int | Number of forks |
| `open_issues` | int | Number of open issues |
| `language` | string | Primary programming language |
| `created_at` | timestamp | Creation date |
| `updated_at` | timestamp | Last update date |
| `commits` | int | Total number of commits |
| `milestones` | int | Total milestones (open + closed) |
| `contributors` | array | List of contributor usernames |
| `size` | int | Repository size in KB |
| `watchers` | int | Number of watchers |
| `has_issues` | bool | Whether issues are enabled |
| `has_wiki` | bool | Whether wiki is enabled |
| `default_branch` | string | Default branch name |
| `license` | string | License type |
| `error` | string | Error message (if any) |

## Performance

- **Parallel Processing**: Utilizes all CPU cores simultaneously
- **Concurrent API Calls**: Each repository is fetched independently
- **Efficient Resource Usage**: Worker pool pattern prevents resource exhaustion
- **Scalable**: Can handle hundreds of repositories efficiently

### Example Performance
- 15 repositories on 8-core machine: ~30-60 seconds (depending on repository size)
- Processing time scales with the largest repository, not the total number

## Error Handling

- Missing token: Server won't start
- Invalid input file: Returns 400 Bad Request
- Repository access errors: Logged in individual repository objects
- API rate limits: Handled gracefully per repository

## Development

### Project Structure
```
go/
├── main.go              # Entry point & server setup
├── config/
│   └── config.go        # Configuration management
├── models/
│   └── repository.go    # Data structures
├── github/
│   └── client.go        # GitHub API client
├── csv/
│   └── reader.go        # CSV input reading
└── server/
    └── handler.go       # HTTP handlers & worker pool
```

### Testing

Use the provided test script:
```bash
./test-server.sh
```

## Notes

- The server processes all repositories before returning the response
- Large repositories (e.g., Linux kernel) may take longer to process
- GitHub API rate limits: 5,000 requests/hour with authentication
- Contributors list may be truncated for repositories with thousands of contributors

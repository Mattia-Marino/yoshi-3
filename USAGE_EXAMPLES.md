# Usage Examples

## Starting the Server

### Basic Start
```bash
cd go
./github-extractor
```

Output:
```
2024/11/06 10:00:00 GitHub Repository Extractor Server
2024/11/06 10:00:00 Using 8 CPU cores for parallel processing
2024/11/06 10:00:00 Server starting on :8080
2024/11/06 10:00:00 Endpoint: GET /extract
2024/11/06 10:00:00 Health check: GET /health
```

### Custom Port
```bash
PORT=3000 ./github-extractor
```

## API Usage Examples

### 1. Health Check

**Request:**
```bash
curl http://localhost:8080/health
```

**Response:**
```json
{
  "status": "ok",
  "cores": 8
}
```

### 2. Extract Repository Data

**Request:**
```bash
# Get absolute path to input file
INPUT_FILE=$(readlink -f ../input.csv)

# Make request
curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}"
```

**Response:**
```json
{
  "repositories": [
    {
      "owner": "tensorflow",
      "repo": "tensorflow",
      "description": "An Open Source Machine Learning Framework for Everyone",
      "stars": 180000,
      "forks": 74000,
      "open_issues": 2000,
      "language": "C++",
      "created_at": "2015-11-07T01:19:20Z",
      "updated_at": "2024-11-06T10:30:15Z",
      "commits": 50000,
      "milestones": 45,
      "contributors": [
        "tensorflower-gardener",
        "hawkinsp",
        "ebrevdo",
        "mrry",
        "gunan",
        ...
      ],
      "size": 250000,
      "watchers": 9000,
      "has_issues": true,
      "has_wiki": true,
      "default_branch": "master",
      "license": "Apache License 2.0"
    },
    {
      "owner": "microsoft",
      "repo": "vscode",
      "description": "Visual Studio Code",
      "stars": 150000,
      "forks": 26000,
      "open_issues": 5000,
      "language": "TypeScript",
      "created_at": "2015-09-03T20:23:38Z",
      "updated_at": "2024-11-06T09:15:22Z",
      "commits": 85000,
      "milestones": 120,
      "contributors": [
        "bpasero",
        "jrieken",
        "mjbvz",
        "joaomoreno",
        ...
      ],
      "size": 180000,
      "watchers": 5000,
      "has_issues": true,
      "has_wiki": false,
      "default_branch": "main",
      "license": "MIT License"
    }
  ],
  "total_count": 2
}
```

### 3. Pretty Print with jq

```bash
INPUT_FILE=$(readlink -f ../input.csv)

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}" \
  | jq .
```

### 4. Save to File

```bash
INPUT_FILE=$(readlink -f ../input.csv)

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}" \
  -o output.json

echo "Response saved to output.json"
```

### 5. Extract Specific Fields

Get only repository names and star counts:
```bash
INPUT_FILE=$(readlink -f ../input.csv)

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}" \
  | jq '.repositories[] | {owner, repo, stars, commits}'
```

### 6. Filter by Language

Get only JavaScript repositories:
```bash
INPUT_FILE=$(readlink -f ../input.csv)

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}" \
  | jq '.repositories[] | select(.language == "JavaScript")'
```

### 7. Top Contributors

Get top 10 contributors for the first repository:
```bash
INPUT_FILE=$(readlink -f ../input.csv)

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}" \
  | jq '.repositories[0].contributors[:10]'
```

## Error Handling Examples

### 1. Missing input_file_path

**Request:**
```bash
curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**
```json
{
  "error": "input_file_path is required"
}
```
Status: 400 Bad Request

### 2. Invalid File Path

**Request:**
```bash
curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d '{"input_file_path": "/nonexistent/file.csv"}'
```

**Response:**
```json
{
  "error": "Failed to read input file: failed to open file /nonexistent/file.csv: no such file or directory"
}
```
Status: 400 Bad Request

### 3. Repository Not Found

When a repository doesn't exist or is private, the error is included in the repository object:

```json
{
  "repositories": [
    {
      "owner": "nonexistent",
      "repo": "repo",
      "error": "Failed to fetch repository: 404 Not Found []"
    }
  ],
  "total_count": 1
}
```
Status: 200 OK (individual errors don't fail the entire request)

## Performance Monitoring

### Monitor Server Logs

```bash
# In one terminal
cd go
./github-extractor

# In another terminal
# Watch the processing
tail -f nohup.out
```

You'll see output like:
```
2024/11/06 10:00:00 Processing 15 repositories using 8 CPU cores
2024/11/06 10:00:01 [Worker 0] Processing tensorflow/tensorflow
2024/11/06 10:00:01 [Worker 1] Processing microsoft/vscode
2024/11/06 10:00:01 [Worker 2] Processing golang/go
...
```

## Integration Examples

### Python

```python
import requests
import json
import os

# Get absolute path
input_path = os.path.abspath("input.csv")

# Make request
response = requests.get(
    "http://localhost:8080/extract",
    json={"input_file_path": input_path}
)

data = response.json()
print(f"Found {data['total_count']} repositories")

for repo in data['repositories']:
    print(f"{repo['owner']}/{repo['repo']}: {repo['stars']} stars, {len(repo['contributors'])} contributors")
```

### Node.js

```javascript
const axios = require('axios');
const path = require('path');

const inputPath = path.resolve('../input.csv');

axios.get('http://localhost:8080/extract', {
  data: {
    input_file_path: inputPath
  }
})
.then(response => {
  console.log(`Found ${response.data.total_count} repositories`);
  
  response.data.repositories.forEach(repo => {
    console.log(`${repo.owner}/${repo.repo}: ${repo.stars} stars`);
  });
})
.catch(error => {
  console.error('Error:', error.message);
});
```

## Production Deployment

### Using systemd

Create `/etc/systemd/system/github-extractor.service`:

```ini
[Unit]
Description=GitHub Repository Extractor
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/yoshi-3/go
Environment="YOSHI_GH_TOKEN=your_token_here"
Environment="PORT=8080"
ExecStart=/path/to/yoshi-3/go/github-extractor
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable github-extractor
sudo systemctl start github-extractor
sudo systemctl status github-extractor
```

### Using Docker

Create `Dockerfile`:
```dockerfile
FROM golang:1.21-alpine

WORKDIR /app
COPY go/ .

RUN go build -o github-extractor

EXPOSE 8080

CMD ["./github-extractor"]
```

Build and run:
```bash
docker build -t github-extractor .
docker run -p 8080:8080 -e YOSHI_GH_TOKEN=your_token github-extractor
```

## Batch Processing

Process multiple input files:

```bash
#!/bin/bash

for csv_file in *.csv; do
    echo "Processing $csv_file..."
    INPUT_PATH=$(readlink -f "$csv_file")
    
    curl -X GET http://localhost:8080/extract \
      -H "Content-Type: application/json" \
      -d "{\"input_file_path\": \"$INPUT_PATH\"}" \
      -o "output_${csv_file%.csv}.json"
    
    echo "Saved to output_${csv_file%.csv}.json"
done
```

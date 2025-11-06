#!/bin/bash
# Quick example of how to use the GitHub Extractor API

# Set your token
# export YOSHI_GH_TOKEN="your_token_here"

# Get absolute path to input.csv
INPUT_FILE=$(readlink -f input.csv)

echo "=== GitHub Repository Extractor ==="
echo ""
echo "1. Health Check:"
curl -s http://localhost:8080/health | jq .

echo ""
echo "2. Extract Repositories:"
echo "   Input file: $INPUT_FILE"
echo ""

curl -X GET http://localhost:8080/extract \
  -H "Content-Type: application/json" \
  -d "{\"input_file_path\": \"$INPUT_FILE\"}" \
  | jq '{
      total: .total_count,
      repositories: [
        .repositories[] | {
          name: "\(.owner)/\(.repo)",
          stars: .stars,
          commits: .commits,
          milestones: .milestones,
          contributors_count: (.contributors | length),
          top_contributors: .contributors[:5]
        }
      ]
    }'

package csv

import (
	"encoding/csv"
	"fmt"
	"os"

	"github-extractor/models"
)

// Reader handles reading repository data from CSV files
type Reader struct {
	filePath string
}

// NewReader creates a new CSV reader
func NewReader(filePath string) *Reader {
	return &Reader{filePath: filePath}
}

// ReadRepositories reads repositories from the CSV file
func (r *Reader) ReadRepositories() ([]models.RepositoryInput, error) {
	file, err := os.Open(r.filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to open file %s: %w", r.filePath, err)
	}
	defer file.Close()

	reader := csv.NewReader(file)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("failed to read CSV: %w", err)
	}

	if len(records) < 2 {
		return nil, fmt.Errorf("CSV file is empty or has no data rows")
	}

	// Validate headers
	headers := records[0]
	if len(headers) < 2 || headers[0] != "owner" || headers[1] != "repo" {
		return nil, fmt.Errorf("invalid CSV headers: expected 'owner,repo'")
	}

	// Parse data rows
	repositories := make([]models.RepositoryInput, 0, len(records)-1)
	for i, record := range records[1:] {
		if len(record) < 2 {
			return nil, fmt.Errorf("invalid record at line %d: not enough columns", i+2)
		}

		repositories = append(repositories, models.RepositoryInput{
			Owner: record[0],
			Repo:  record[1],
		})
	}

	return repositories, nil
}

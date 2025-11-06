package csv

import (
	"encoding/csv"
	"fmt"
	"os"

	"github-extractor/models"
)

// Writer handles writing repository data to CSV files
type Writer struct {
	filePath string
}

// NewWriter creates a new CSV writer
func NewWriter(filePath string) *Writer {
	return &Writer{filePath: filePath}
}

// WriteRepositories writes repository information to CSV file
func (w *Writer) WriteRepositories(repos []models.RepositoryInfo) error {
	file, err := os.Create(w.filePath)
	if err != nil {
		return fmt.Errorf("failed to create file %s: %w", w.filePath, err)
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()

	// Write headers
	if len(repos) > 0 {
		headers := repos[0].ToCSVHeaders()
		if err := writer.Write(headers); err != nil {
			return fmt.Errorf("failed to write headers: %w", err)
		}
	}

	// Write data rows
	for _, repo := range repos {
		row := repo.ToCSVRow()
		if err := writer.Write(row); err != nil {
			return fmt.Errorf("failed to write row for %s/%s: %w", repo.Owner, repo.Repo, err)
		}
	}

	if err := writer.Error(); err != nil {
		return fmt.Errorf("CSV writer error: %w", err)
	}

	return nil
}

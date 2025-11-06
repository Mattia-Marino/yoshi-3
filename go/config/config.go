package config

import (
	"fmt"
	"os"
)

const (
	// TokenEnvVar is the environment variable name for GitHub token
	TokenEnvVar = "YOSHI_GH_TOKEN"
)

// Config holds application configuration
type Config struct {
	GitHubToken string
	InputFile   string
	OutputFile  string
}

// Load loads configuration from environment and returns Config
func Load() (*Config, error) {
	token := os.Getenv(TokenEnvVar)
	if token == "" {
		return nil, fmt.Errorf("environment variable %s is not set", TokenEnvVar)
	}

	return &Config{
		GitHubToken: token,
		InputFile:   "input.csv",
		OutputFile:  "output.csv",
	}, nil
}

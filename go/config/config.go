package config

import (
	"fmt"
	"os"
)

const (
	// TokenEnvVar is the environment variable name for GitHub token
	TokenEnvVar = "YOSHI_GH_TOKEN"
	// DefaultPort is the default HTTP server port
	DefaultPort = "8080"
)

// Config holds application configuration
type Config struct {
	GitHubToken string
	Port        string
}

// Load loads configuration from environment and returns Config
func Load() (*Config, error) {
	token := os.Getenv(TokenEnvVar)
	if token == "" {
		return nil, fmt.Errorf("environment variable %s is not set", TokenEnvVar)
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = DefaultPort
	}

	return &Config{
		GitHubToken: token,
		Port:        port,
	}, nil
}

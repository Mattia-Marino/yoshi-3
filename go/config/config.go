package config

import (
	"fmt"
	"os"
)

const (
	TokenEnvVar = "YOSHI_GH_TOKEN" // Environment variable name for GitHub token
	DefaultPort = "6001"           // Default HTTP server port

	// gRPC
	DefaultGRPCAddress = "localhost:50051" // Default gRPC processor service address

	// Logging
	DefaultLogFile  = "./gh-extractor.log"
	DefaultLogLevel = "info"
)

// Application configuration
type Config struct {
	GitHubToken string
	Port        string
	LogFile     string
	LogLevel    string
	GRPCAddress string
}

// Load configuration from environment and returns Config or error
func LoadConfig() (*Config, error) {
	// Set GitHub token. Return error if not present
	token := getEnv(TokenEnvVar, "")
	if token == "" {
		return nil, fmt.Errorf("environment variable %s is not set", TokenEnvVar)
	}

	// Set server port
	port := getEnv("PORT", DefaultPort)

	// gRPC address
	grpcAddr := getEnv("GRPC_ADDRESS", DefaultGRPCAddress)

	// Logging
	logFile := getEnv("LOG_FILE", DefaultLogFile)
	logLevel := getEnv("LOG_LEVEL", DefaultLogLevel)

	// If everything went alright, return correct values
	return &Config{
		GitHubToken: token,
		Port:        port,
		GRPCAddress: grpcAddr,
		LogFile:     logFile,
		LogLevel:    logLevel,
	}, nil
}

// LoadLoggingConfig returns only logging-related values so the logger can be
// initialized before validating required app config.
func LoadLoggingConfig() (logFile, logLevel string) {
	return getEnv("LOG_FILE", DefaultLogFile), getEnv("LOG_LEVEL", DefaultLogLevel)
}

// Utility function to set an environment variable or its default value
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}

	return defaultValue
}

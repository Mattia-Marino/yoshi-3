package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"github-extractor/config"
	"github-extractor/github"
	"github-extractor/server"

	_ "github-extractor/docs"
	"github-extractor/logger"
	"github-extractor/middleware"

	stdlog "log"

	"github.com/sirupsen/logrus"
)

// @title GitHub Repository Extractor API
// @version 1.0
// @description This is a server to extract detailed information from GitHub repositories.
// @host localhost:6001
// @BasePath /
func main() {

	// Initialize logger
	logFile, logLevel := config.LoadLoggingConfig()
	if logLevel == "" {
		logLevel = "info"
	}
	appLogger := logger.Init(logFile, logLevel)
	appLogger.WithField("level", appLogger.Level.String()).Info("Logger configured")

	// Redirect standard library logger output into logrus so other packages' logs
	// go through the same writer/rotator and formatting.
	stdlog.SetOutput(appLogger.Writer())
	stdlog.SetFlags(0)

	// Startup message as debug-level (logger already set to debug if LOG_LEVEL=debug)
	appLogger.Info("Starting the server...")

	// Load configuration
	cfg, err := config.LoadConfig()
	if err != nil {
		appLogger.WithField("error", err).Fatal("Configuration error")
	}

	// Set GOMAXPROCS to use all available CPU cores
	numCPU := runtime.NumCPU()
	runtime.GOMAXPROCS(numCPU)

	appLogger.Info("GitHub Repository Extractor Server")
	appLogger.Infof("Using %d CPU cores for parallel processing", numCPU)

	// Create GitHub client
	ghClient := github.NewClient(cfg.GitHubToken, appLogger)

	// Initialize service with worker pool
	service := server.NewService(ghClient, appLogger)

	// Initialize handler
	ghHandler := server.NewHandler(service, appLogger)

	// Setup routes
	router := server.SetupRoutes(ghHandler)

	// Wrap router with logging middleware
	handler := middleware.LoggingMiddleware(appLogger)(router)

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      handler,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 300 * time.Second, // aumentato per risposte lunghe
		IdleTimeout:  60 * time.Second,
	}

	// Start server in a goroutine
	go func() {
		appLogger.WithFields(logrus.Fields{"port": cfg.Port}).Info("Server is running")
		appLogger.WithField("swagger", "http://localhost:"+cfg.Port+"/swagger/").Info("API docs")
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			appLogger.WithField("error", err).Fatal("Server failed to start")
		}
	}()

	// Wait for interrupt signal to gracefully shutdown the server
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	appLogger.Info("Shutting down server...")

	// Graceful shutdown with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		appLogger.WithField("error", err).Fatal("Server forced to shutdown")
	}
	appLogger.Info("Server exited")
}

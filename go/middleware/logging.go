package middleware

import (
	"net/http"
	"time"

	"github.com/sirupsen/logrus"
)

type responseWriter struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (rw *responseWriter) WriteHeader(status int) {
	rw.status = status
	rw.ResponseWriter.WriteHeader(status)
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	if rw.status == 0 {
		rw.status = http.StatusOK
	}
	n, err := rw.ResponseWriter.Write(b)
	rw.bytes += n
	return n, err
}

// LoggingMiddleware returns middleware that logs request start and completion.
func LoggingMiddleware(logger *logrus.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			// If the request is for health or readiness checks, only log them when
			// the logger is set to Debug (or more verbose). This avoids noisy logs
			// from frequent probes at higher log levels.
			if r.URL.Path == "/health" || r.URL.Path == "/ready" {
				// Prefer the helper when available; fall back to numeric level check
				// for older logrus versions.
				if !logger.IsLevelEnabled(logrus.DebugLevel) {
					// If Debug is not enabled, skip structured logging for probes.
					next.ServeHTTP(w, r)
					return
				}
			}

			rw := &responseWriter{ResponseWriter: w}

			// Include the raw query and parsed query params so callers can see
			// request-specific parameters (e.g. ?email=...)
			logger.WithFields(logrus.Fields{
				"method":       r.Method,
				"path":         r.URL.Path,
				"request_uri":  r.RequestURI,
				"raw_query":    r.URL.RawQuery,
				"query_params": r.URL.Query(),
				"remote":       r.RemoteAddr,
				"user_agent":   r.UserAgent(),
				"headers":      r.Header,
			}).Info("request started")

			next.ServeHTTP(rw, r)

			latency := time.Since(start)
			logger.WithFields(logrus.Fields{
				"method":       r.Method,
				"path":         r.URL.Path,
				"request_uri":  r.RequestURI,
				"raw_query":    r.URL.RawQuery,
				"query_params": r.URL.Query(),
				"status":       rw.status,
				"bytes":        rw.bytes,
				"durationMs":   latency.Milliseconds(),
				"headers":      r.Header,
			}).Info("request completed")
		})
	}
}

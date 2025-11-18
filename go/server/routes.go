package server

import (
	"github.com/gorilla/mux"
)

func SetupRoutes(handler *Handler) *mux.Router {
	r := mux.NewRouter()

	r.HandleFunc("/health", handler.HealthCheckHandler).Methods("GET")
	r.HandleFunc("/extract", handler.ExtractHandler).Methods("POST")

	return r
}

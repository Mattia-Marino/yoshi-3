package server

import (
	"github.com/gorilla/mux"
	httpSwagger "github.com/swaggo/http-swagger"
)

func SetupRoutes(handler *Handler) *mux.Router {
	r := mux.NewRouter()

	r.HandleFunc("/health", handler.HealthCheckHandler).Methods("GET")
	r.HandleFunc("/extract", handler.ExtractHandler).Methods("POST")

	// Swagger
	r.PathPrefix("/swagger/").Handler(httpSwagger.WrapHandler)

	return r
}

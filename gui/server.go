package main

import (
	"log"
	"net/http"
	"os"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	staticDir := os.Getenv("STATIC_DIR")
	if staticDir == "" {
		staticDir = "."
	}

	mux := http.NewServeMux()

	// Serve static assets (css/, javascript/, images/, audio/)
	fs := http.FileServer(http.Dir(staticDir))
	mux.Handle("/css/", fs)
	mux.Handle("/javascript/", fs)
	mux.Handle("/images/", fs)
	mux.Handle("/audio/", fs)

	// Serve index.html for the root path
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, staticDir+"/html/index.html")
	})

	log.Printf("GUI server listening on :%s", port)
	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatalf("server error: %v", err)
	}
}

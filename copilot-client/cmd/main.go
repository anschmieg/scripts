package main

import (
	"go-app/internal/app"
	"log"
	"net/http"
)

func main() {
	a := app.NewApp()

	// Authenticate (using methods from Zed) and retrieve new authentication details if necessary.
	oauthToken := "your-oauth-token-here" // Replace with the actual OAuth token
	apiKey, err := a.GetAPIKey(oauthToken)
	if err != nil {
		log.Fatalf("Failed to retrieve API key: %v", err)
	}
	log.Printf("Retrieved API key: %s", apiKey)

	// Start the server, exposing the OpenAI-compatible endpoints.
	log.Println("Starting server on :8080...")
	if err := http.ListenAndServe(":8080", a.Router); err != nil {
		log.Fatalf("Could not start server: %v", err)
	}
}

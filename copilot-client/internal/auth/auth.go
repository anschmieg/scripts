package auth

import (
	"errors"
	"os"
	"strings"
)

// Service provides authentication-related functionalities.
type Service struct {
	isAuthenticated bool
}

// NewService creates and returns a new instance of the Service struct.
func NewService() *Service {
	return &Service{isAuthenticated: false}
}

// GetStatus returns the authentication status of the service.
func (s *Service) GetStatus() string {
	if s.isAuthenticated {
		return "Authenticated"
	}
	return "Not Authenticated"
}

// Authenticate sets the service's authentication status to true if not already authenticated.
func (s *Service) Authenticate() error {
	if s.isAuthenticated {
		return errors.New("Already authenticated")
	}
	s.isAuthenticated = true
	return nil
}

// VerifyAPIKey checks the provided API key against the comma-separated list in the VALID_API_KEYS environment variable.
func VerifyAPIKey(apiKey string) bool {
	validKeys := os.Getenv("VALID_API_KEYS")
	keys := strings.Split(validKeys, ",")
	for _, key := range keys {
		if apiKey == strings.TrimSpace(key) {
			return true
		}
	}
	return false
}

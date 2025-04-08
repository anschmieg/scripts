package llm

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"go-app/pkg/models"
	"go-app/pkg/utils"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

const (
	// API endpoints
	CopilotChatCompletionURL = "https://api.githubcopilot.com/chat/completions"
	OpenAIChatCompletionURL  = "https://api.openai.com/v1/chat/completions"
	AnthropicCompletionURL   = "https://api.anthropic.com/v1/messages"
	GoogleAICompletionURL    = "https://generativelanguage.googleapis.com/v1/models"

	// Minimal account age required for using LLM features
	MinAccountAgeDays = 7
)

var (
	ErrProviderNotSupported = errors.New("provider not supported")
	ErrAccountTooYoung      = errors.New("account must be older than 7 days to use LLM features")
)

// LLMService manages LLM API interactions
type LLMService struct {
	config      *Config
	httpClient  *http.Client
	usageLock   sync.RWMutex
	userUsage   map[uint64]models.ModelUsage
	activeUsers map[string]models.ActiveUserCount // key is provider:model
}

// NewLLMService creates a new LLM service
func NewLLMService() *LLMService {
	return &LLMService{
		config:      GetConfig(),
		httpClient:  &http.Client{Timeout: 30 * time.Second},
		userUsage:   make(map[uint64]models.ModelUsage),
		activeUsers: make(map[string]models.ActiveUserCount),
	}
}

// CompletionRequest contains the data needed for a completion request
type CompletionRequest struct {
	Provider        models.LanguageModelProvider
	Model           string
	ProviderRequest string // JSON payload for the provider
	Token           *models.LLMToken
	CountryCode     *string
	CurrentSpending uint32
}

// GetActiveUserCount returns active users for a model
func (s *LLMService) GetActiveUserCount(provider models.LanguageModelProvider, model string) models.ActiveUserCount {
	key := fmt.Sprintf("%s:%s", provider, model)
	s.usageLock.RLock()
	defer s.usageLock.RUnlock()

	count, exists := s.activeUsers[key]
	if !exists {
		return models.ActiveUserCount{
			UsersInRecentMinutes: 1,
			UsersInRecentDays:    1,
		}
	}
	return count
}

// RecordUsage records token usage for a user and model
func (s *LLMService) RecordUsage(userId uint64, provider models.LanguageModelProvider, model string, usage models.TokenUsage) {
	s.usageLock.Lock()
	defer s.usageLock.Unlock()

	key := fmt.Sprintf("%d:%s:%s", userId, provider, model)
	existing, exists := s.userUsage[userId]

	if !exists {
		existing = models.ModelUsage{
			UserID:                 userId,
			Provider:               provider,
			Model:                  model,
			RequestsThisMinute:     1,
			TokensThisMinute:       usage.Input + usage.Output,
			InputTokensThisMinute:  usage.Input,
			OutputTokensThisMinute: usage.Output,
			TokensThisDay:          usage.Input + usage.Output,
		}
	} else {
		existing.RequestsThisMinute++
		existing.TokensThisMinute += usage.Input + usage.Output
		existing.InputTokensThisMinute += usage.Input
		existing.OutputTokensThisMinute += usage.Output
		existing.TokensThisDay += usage.Input + usage.Output
	}

	s.userUsage[userId] = existing

	// Update active user counts
	modelKey := fmt.Sprintf("%s:%s", provider, model)
	activeCount, exists := s.activeUsers[modelKey]
	if !exists {
		activeCount = models.ActiveUserCount{
			UsersInRecentMinutes: 1,
			UsersInRecentDays:    1,
		}
	}
	// In a real implementation, we would track unique users over time
	s.activeUsers[modelKey] = activeCount
}

// GetModelUsage returns the current usage for a user and model
func (s *LLMService) GetModelUsage(userId uint64, provider models.LanguageModelProvider, model string) models.ModelUsage {
	s.usageLock.RLock()
	defer s.usageLock.RUnlock()

	existing, exists := s.userUsage[userId]
	if !exists {
		return models.ModelUsage{
			UserID:   userId,
			Provider: provider,
			Model:    model,
		}
	}
	return existing
}

// PerformCompletion handles an LLM completion request
func (s *LLMService) PerformCompletion(req CompletionRequest) (*http.Response, error) {
	// Check account age
	accountAgeInDays := time.Since(req.Token.AccountCreatedAt).Hours() / 24
	if accountAgeInDays < MinAccountAgeDays && !req.Token.IsStaff && !req.Token.HasLLMSubscription {
		return nil, ErrAccountTooYoung
	}

	// Normalize model name
	model := normalizeModelName(req.Provider, req.Model)

	// Get current usage
	usage := s.GetModelUsage(req.Token.UserID, req.Provider, model)
	activeUsers := s.GetActiveUserCount(req.Provider, model)

	// Validate access
	if err := ValidateAccess(req.Token, req.CountryCode, req.Provider, model,
		usage, activeUsers, req.CurrentSpending); err != nil {
		return nil, err
	}

	// Route to appropriate provider
	var resp *http.Response
	var err error

	switch req.Provider {
	case models.ProviderCopilot:
		resp, err = s.callCopilotAPI(req.ProviderRequest)
	case models.ProviderOpenAI:
		resp, err = s.callOpenAIAPI(req.ProviderRequest)
	case models.ProviderAnthropic:
		resp, err = s.callAnthropicAPI(req.ProviderRequest, req.Token.IsStaff)
	case models.ProviderGoogle:
		resp, err = s.callGoogleAIAPI(req.ProviderRequest)
	default:
		return nil, ErrProviderNotSupported
	}

	return resp, err
}

// normalizeModelName ensures we use the correct model name for the provider
func normalizeModelName(provider models.LanguageModelProvider, name string) string {
	models := DefaultModels()
	var bestMatch string
	var bestMatchLength int

	for _, model := range models {
		if model.Provider == provider && strings.HasPrefix(name, model.Name) {
			if len(model.Name) > bestMatchLength {
				bestMatch = model.Name
				bestMatchLength = len(model.Name)
			}
		}
	}

	if bestMatch != "" {
		return bestMatch
	}

	return name
}

// callCopilotAPI calls the GitHub Copilot API
func (s *LLMService) callCopilotAPI(providerRequest string) (*http.Response, error) {
	apiKey := s.config.CopilotApiKey
	if apiKey == "" {
		return nil, errors.New("Copilot API key not configured")
	}

	var requestData map[string]interface{}
	if err := json.Unmarshal([]byte(providerRequest), &requestData); err != nil {
		return nil, err
	}

	return utils.CallAPIWithBody(CopilotChatCompletionURL, "application/json", apiKey, requestData)
}

// callOpenAIAPI calls the OpenAI API
func (s *LLMService) callOpenAIAPI(providerRequest string) (*http.Response, error) {
	apiKey := s.config.OpenAIApiKey
	if apiKey == "" {
		return nil, errors.New("OpenAI API key not configured")
	}

	var requestData map[string]interface{}
	if err := json.Unmarshal([]byte(providerRequest), &requestData); err != nil {
		return nil, err
	}

	return utils.CallAPIWithBody(OpenAIChatCompletionURL, "application/json", apiKey, requestData)
}

// callAnthropicAPI calls the Anthropic API
func (s *LLMService) callAnthropicAPI(providerRequest string, isStaff bool) (*http.Response, error) {
	var apiKey string
	if isStaff && s.config.AnthropicStaffApiKey != "" {
		apiKey = s.config.AnthropicStaffApiKey
	} else {
		apiKey = s.config.AnthropicApiKey
	}

	if apiKey == "" {
		return nil, errors.New("Anthropic API key not configured")
	}

	var requestData map[string]interface{}
	if err := json.Unmarshal([]byte(providerRequest), &requestData); err != nil {
		return nil, err
	}

	// Modify model name if needed to use the latest version
	if model, ok := requestData["model"].(string); ok {
		switch model {
		case "claude-3-5-sonnet":
			requestData["model"] = "claude-3-5-sonnet-20240620"
		case "claude-3-7-sonnet":
			requestData["model"] = "claude-3-7-sonnet-20240307"
		case "claude-3-opus":
			requestData["model"] = "claude-3-opus-20240229"
		case "claude-3-haiku":
			requestData["model"] = "claude-3-haiku-20240307"
		case "claude-3-sonnet":
			requestData["model"] = "claude-3-sonnet-20240229"
		}
	}

	body, err := json.Marshal(requestData)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", AnthropicCompletionURL, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-api-key", apiKey)
	req.Header.Set("anthropic-version", "2023-06-01")

	return s.httpClient.Do(req)
}

// callGoogleAIAPI calls the Google AI API
func (s *LLMService) callGoogleAIAPI(providerRequest string) (*http.Response, error) {
	apiKey := s.config.GoogleAIApiKey
	if apiKey == "" {
		return nil, errors.New("Google AI API key not configured")
	}

	var requestData map[string]interface{}
	if err := json.Unmarshal([]byte(providerRequest), &requestData); err != nil {
		return nil, err
	}

	// Extract model name
	model, ok := requestData["model"].(string)
	if !ok {
		return nil, errors.New("missing model in request")
	}

	// Construct Google AI API URL with model name
	url := fmt.Sprintf("%s/%s:generateContent?key=%s", GoogleAICompletionURL, model, apiKey)

	body, err := json.Marshal(requestData)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")

	return s.httpClient.Do(req)
}

// ProcessStreamingResponse processes a streaming response from any provider
func (s *LLMService) ProcessStreamingResponse(resp *http.Response, userID uint64, provider models.LanguageModelProvider, model string) (io.ReadCloser, error) {
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		return nil, fmt.Errorf("provider returned error: %s", string(body))
	}

	// In a full implementation, this would track token usage from the streaming response
	// For simplicity, we'll just return the response body as-is

	return resp.Body, nil
}

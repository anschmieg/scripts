// Package llm implements language model integration for various AI providers.
package llm

import (
	"go-app/pkg/models"
	"go-app/pkg/utils"
	"os"
	"sync"
)

// Config contains configuration for the LLM service including API keys,
// enabled providers, and spending limits. This centralizes all configuration
// related to language model providers.
type Config struct {
	// OpenAIApiKey is the API key for accessing OpenAI services
	OpenAIApiKey string
	// CopilotApiKey is the API key for accessing GitHub Copilot Chat
	CopilotApiKey string
	// AnthropicApiKey is the API key for accessing Anthropic models
	AnthropicApiKey string
	// AnthropicStaffApiKey is a special API key for staff access to Anthropic models
	AnthropicStaffApiKey string
	// GoogleAIApiKey is the API key for accessing Google AI models
	GoogleAIApiKey string
	// EnabledProviders is the list of currently enabled LLM providers
	EnabledProviders []models.LanguageModelProvider
	// ClosedBetaModelName is the name of a model that's in closed beta (if any)
	ClosedBetaModelName string
	// DefaultMaxMonthlySpend is the default spending limit in cents per month
	DefaultMaxMonthlySpend uint32
	// FreeTierMonthlyAllowance is the free usage allowance in cents per month
	FreeTierMonthlyAllowance uint32
}

var (
	// config is the singleton instance of the configuration
	config *Config
	// configOnce ensures the configuration is initialized only once
	configOnce sync.Once
)

// GetConfig returns the singleton LLM configuration.
// On first call, it initializes the configuration by loading values from
// environment variables and local configuration files.
//
// It attempts to load the Copilot API key from the following sources in order:
// 1. COPILOT_API_KEY environment variable
// 2. Local GitHub Copilot configuration file (~/.config/github-copilot/apps.json)
//
// Returns a pointer to the configuration structure.
func GetConfig() *Config {
	configOnce.Do(func() {
		// Try to load Copilot API key from local config if not in environment
		copilotApiKey := os.Getenv("COPILOT_API_KEY")
		if copilotApiKey == "" {
			if token, err := utils.GetCopilotToken(); err == nil {
				copilotApiKey = token
			}
		}

		config = &Config{
			OpenAIApiKey:             os.Getenv("OPENAI_API_KEY"),
			CopilotApiKey:            copilotApiKey,
			AnthropicApiKey:          os.Getenv("ANTHROPIC_API_KEY"),
			AnthropicStaffApiKey:     os.Getenv("ANTHROPIC_STAFF_API_KEY"),
			GoogleAIApiKey:           os.Getenv("GOOGLE_AI_API_KEY"),
			EnabledProviders:         defaultEnabledProviders(copilotApiKey),
			DefaultMaxMonthlySpend:   1000, // $10.00 in cents
			FreeTierMonthlyAllowance: 1000, // $10.00 in cents
		}
	})
	return config
}

// defaultEnabledProviders determines which LLM providers should be enabled
// based on available API keys. A provider is only enabled if its API key is available.
//
// This prevents configuration errors where the system might try to use a provider
// without proper authentication.
//
// Parameters:
//   - copilotApiKey: The GitHub Copilot API key (passed separately as it might be
//     retrieved from local config rather than environment)
//
// Returns a slice of enabled LanguageModelProvider values.
func defaultEnabledProviders(copilotApiKey string) []models.LanguageModelProvider {
	providers := []models.LanguageModelProvider{}

	if copilotApiKey != "" {
		providers = append(providers, models.ProviderCopilot)
	}
	if os.Getenv("OPENAI_API_KEY") != "" {
		providers = append(providers, models.ProviderOpenAI)
	}
	if os.Getenv("ANTHROPIC_API_KEY") != "" {
		providers = append(providers, models.ProviderAnthropic)
	}
	if os.Getenv("GOOGLE_AI_API_KEY") != "" {
		providers = append(providers, models.ProviderGoogle)
	}

	return providers
}

// DefaultModels returns the default models for each provider with their
// configuration settings including rate limits. This defines all the language
// models available in the system along with their capabilities.
//
// Returns a slice of LanguageModel structures defining each model's properties.
func DefaultModels() []models.LanguageModel {
	return []models.LanguageModel{
		{
			ID:                       "copilot-chat",
			Name:                     "copilot-chat",
			Provider:                 models.ProviderCopilot,
			MaxRequestsPerMinute:     25,
			MaxTokensPerMinute:       5000,
			MaxInputTokensPerMinute:  2500,
			MaxOutputTokensPerMinute: 2500,
			MaxTokensPerDay:          100000,
			Enabled:                  true,
		},
		{
			ID:                       "gpt-4",
			Name:                     "gpt-4",
			Provider:                 models.ProviderOpenAI,
			MaxRequestsPerMinute:     20,
			MaxTokensPerMinute:       4000,
			MaxInputTokensPerMinute:  2000,
			MaxOutputTokensPerMinute: 2000,
			MaxTokensPerDay:          80000,
			Enabled:                  true,
		},
		{
			ID:                       "claude-3-opus",
			Name:                     "claude-3-opus",
			Provider:                 models.ProviderAnthropic,
			MaxRequestsPerMinute:     15,
			MaxTokensPerMinute:       3000,
			MaxInputTokensPerMinute:  1500,
			MaxOutputTokensPerMinute: 1500,
			MaxTokensPerDay:          60000,
			Enabled:                  true,
		},
	}
}

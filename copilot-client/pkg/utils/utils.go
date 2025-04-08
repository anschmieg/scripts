package utils

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
)

// CopilotChatCompletionURL is the endpoint for GitHub Copilot chat completions.
const CopilotChatCompletionURL = "https://api.githubcopilot.com/chat/completions"

// SomeUtilityFunction performs a specific utility task.
func SomeUtilityFunction(input string) string {
	// Implement the utility logic here
	return "Processed: " + input
}

// CallOpenAIEndpoint sends a request to the OpenAI endpoint and returns the response.
func CallOpenAIEndpoint(apiKey string, payload map[string]interface{}) (map[string]interface{}, error) {
	// Ensure payload adheres to OpenAI schema
	if _, ok := payload["model"]; !ok {
		return nil, errors.New("payload must include 'model'")
	}
	if _, ok := payload["messages"]; !ok {
		return nil, errors.New("payload must include 'messages'")
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", CopilotChatCompletionURL, bytes.NewBuffer(body))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, errors.New("failed to call OpenAI endpoint: " + resp.Status)
	}

	var response struct {
		ID      string `json:"id"`
		Object  string `json:"object"`
		Created int64  `json:"created"`
		Model   string `json:"model"`
		Choices []struct {
			Message struct {
				Role    string `json:"role"`
				Content string `json:"content"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
			Index        int    `json:"index"`
		} `json:"choices"`
		Usage struct {
			PromptTokens     int `json:"prompt_tokens"`
			CompletionTokens int `json:"completion_tokens"`
			TotalTokens      int `json:"total_tokens"`
		} `json:"usage"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, err
	}

	// Convert response to a generic map for flexibility
	responseMap := map[string]interface{}{
		"id":      response.ID,
		"object":  response.Object,
		"created": response.Created,
		"model":   response.Model,
		"choices": response.Choices,
		"usage":   response.Usage,
	}

	return responseMap, nil
}

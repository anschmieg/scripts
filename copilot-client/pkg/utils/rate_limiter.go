package utils

import (
	"sync"
	"time"
)

// RateLimiter is a structure that implements a token bucket algorithm for rate limiting.
type RateLimiter struct {
	rate      int
	interval  time.Duration
	tokens    int
	lastCheck time.Time
	mu        sync.Mutex
}

// NewRateLimiter creates a new RateLimiter with the specified rate.
func NewRateLimiter(rate int) *RateLimiter {
	return &RateLimiter{
		rate:      rate,
		interval:  time.Second,
		tokens:    rate,
		lastCheck: time.Now(),
	}
}

// Allow determines whether a request is permitted based on the rate-limiting rules.
// It returns true if the request is allowed, otherwise false.
func (rl *RateLimiter) Allow() bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(rl.lastCheck)
	rl.lastCheck = now

	rl.tokens += int(elapsed / rl.interval)
	if rl.tokens > rl.rate {
		rl.tokens = rl.rate
	}

	if rl.tokens > 0 {
		rl.tokens--
		return true
	}

	return false
}

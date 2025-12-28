"""
S.S.I. SHADOW - Core Module Tests
Tests for exceptions, retry, and circuit breaker.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from core.exceptions import (
    SSIShadowException,
    ValidationException,
    AuthenticationException,
    RateLimitException,
    PlatformAPIException,
    DatabaseException,
    CircuitBreakerOpenException,
    ErrorCategory,
    ErrorSeverity,
    exception_to_http_status,
    is_retryable_exception
)
from core.retry import (
    retry_async,
    retry_sync,
    calculate_delay,
    RetryConfig,
    RetryStrategy,
    RetryExhausted
)
from core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    circuit_breaker
)


# =============================================================================
# EXCEPTION TESTS
# =============================================================================

class TestSSIShadowException:
    """Tests for base exception class."""
    
    def test_basic_exception(self):
        exc = SSIShadowException("Test error", error_code="TEST_001")
        assert exc.message == "Test error"
        assert exc.error_code == "TEST_001"
        assert exc.category == ErrorCategory.INTERNAL
        assert exc.severity == ErrorSeverity.MEDIUM
    
    def test_exception_to_dict(self):
        exc = SSIShadowException(
            "Test error",
            error_code="TEST_001",
            details={"field": "value"}
        )
        data = exc.to_dict()
        assert data["error"] == "TEST_001"
        assert data["message"] == "Test error"
        assert data["details"]["field"] == "value"
    
    def test_retryable_exception(self):
        rate_limit = RateLimitException("Rate limited", retry_after=60)
        assert rate_limit.is_retryable is True
        assert rate_limit.retry_after == 60
        
        validation = ValidationException("Invalid field")
        assert validation.is_retryable is False


class TestValidationException:
    """Tests for validation exceptions."""
    
    def test_with_field(self):
        exc = ValidationException("Invalid email", field="email", value="not-an-email")
        assert exc.details["field"] == "email"
        assert "not-an-email" in exc.details["value"]
    
    def test_http_status(self):
        exc = ValidationException("Invalid")
        status = exception_to_http_status(exc)
        assert status == 400


class TestAuthenticationException:
    """Tests for authentication exceptions."""
    
    def test_basic_auth_error(self):
        exc = AuthenticationException("Token expired")
        assert exc.category == ErrorCategory.AUTHENTICATION
    
    def test_http_status(self):
        exc = AuthenticationException()
        status = exception_to_http_status(exc)
        assert status == 401


class TestRateLimitException:
    """Tests for rate limit exceptions."""
    
    def test_with_retry_after(self):
        exc = RateLimitException(
            "Rate limit exceeded",
            limit=100,
            window_seconds=60,
            retry_after=30
        )
        assert exc.details["limit"] == 100
        assert exc.details["window_seconds"] == 60
        assert exc.retry_after == 30
    
    def test_http_status(self):
        exc = RateLimitException()
        status = exception_to_http_status(exc)
        assert status == 429


class TestPlatformAPIException:
    """Tests for platform API exceptions."""
    
    def test_meta_exception(self):
        from core.exceptions import MetaAPIException
        exc = MetaAPIException("API error", status_code=400)
        assert exc.platform == "meta"
        assert exc.status_code == 400
    
    def test_google_exception(self):
        from core.exceptions import GoogleAdsAPIException
        exc = GoogleAdsAPIException("API error")
        assert exc.platform == "google_ads"


# =============================================================================
# RETRY TESTS
# =============================================================================

class TestRetryAsync:
    """Tests for async retry decorator."""
    
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        call_count = 0
        
        @retry_async(max_retries=3)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await successful_func()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        call_count = 0
        
        @retry_async(max_retries=3, base_delay=0.01)
        async def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Failed")
            return "success"
        
        result = await eventually_succeeds()
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        @retry_async(max_retries=2, base_delay=0.01)
        async def always_fails():
            raise ConnectionError("Always fails")
        
        with pytest.raises(RetryExhausted) as exc_info:
            await always_fails()
        
        assert exc_info.value.details["attempts"] == 3
    
    @pytest.mark.asyncio
    async def test_non_retryable_exception(self):
        @retry_async(
            exceptions=(ConnectionError,),
            max_retries=3
        )
        async def raises_value_error():
            raise ValueError("Not retryable")
        
        with pytest.raises(ValueError):
            await raises_value_error()


class TestCalculateDelay:
    """Tests for delay calculation."""
    
    def test_exponential_delay(self):
        config = RetryConfig(
            base_delay=1.0,
            max_delay=60.0,
            strategy=RetryStrategy.EXPONENTIAL,
            jitter_factor=0
        )
        
        delay0 = calculate_delay(0, config)
        delay1 = calculate_delay(1, config)
        delay2 = calculate_delay(2, config)
        
        assert delay0 == 1.0
        assert delay1 == 2.0
        assert delay2 == 4.0
    
    def test_max_delay_cap(self):
        config = RetryConfig(
            base_delay=10.0,
            max_delay=20.0,
            strategy=RetryStrategy.EXPONENTIAL
        )
        
        delay = calculate_delay(10, config)
        assert delay <= 20.0
    
    def test_fixed_delay(self):
        config = RetryConfig(
            base_delay=5.0,
            strategy=RetryStrategy.FIXED
        )
        
        delay0 = calculate_delay(0, config)
        delay5 = calculate_delay(5, config)
        
        assert delay0 == 5.0
        assert delay5 == 5.0


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for circuit breaker."""
    
    @pytest.mark.asyncio
    async def test_closed_state_success(self):
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        async def success():
            return "ok"
        
        result = await breaker.call(success)
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_opens_after_failures(self):
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        
        async def failing():
            raise ConnectionError("Failed")
        
        for _ in range(3):
            try:
                await breaker.call(failing)
            except ConnectionError:
                pass
        
        assert breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_open_rejects_requests(self):
        breaker = CircuitBreaker(name="test", failure_threshold=2)
        
        async def failing():
            raise ConnectionError("Failed")
        
        # Trigger failures to open
        for _ in range(2):
            try:
                await breaker.call(failing)
            except ConnectionError:
                pass
        
        # Should raise CircuitBreakerOpenException
        with pytest.raises(CircuitBreakerOpenException):
            await breaker.call(failing)
    
    @pytest.mark.asyncio
    async def test_half_open_recovery(self):
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout=0.1,
            half_open_max_calls=2
        )
        
        call_count = 0
        
        async def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Failed")
            return "ok"
        
        # Open the circuit
        for _ in range(2):
            try:
                await breaker.call(sometimes_fails)
            except ConnectionError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Should transition to half-open and succeed
        result = await breaker.call(sometimes_fails)
        assert result == "ok"
    
    @pytest.mark.asyncio
    async def test_reset(self):
        breaker = CircuitBreaker(name="test", failure_threshold=2)
        
        async def failing():
            raise ConnectionError()
        
        # Open the circuit
        for _ in range(2):
            try:
                await breaker.call(failing)
            except ConnectionError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Reset
        await breaker.reset()
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_usage(self):
        @circuit_breaker(name="test_decorator", failure_threshold=3)
        async def protected_func():
            return "protected"
        
        result = await protected_func()
        assert result == "protected"


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_is_retryable_exception(self):
        assert is_retryable_exception(ConnectionError()) is True
        assert is_retryable_exception(TimeoutError()) is True
        assert is_retryable_exception(ValueError()) is False
        
        rate_limit = RateLimitException("Rate limited")
        assert is_retryable_exception(rate_limit) is True
    
    def test_exception_to_http_status(self):
        assert exception_to_http_status(ValidationException("")) == 400
        assert exception_to_http_status(AuthenticationException("")) == 401
        assert exception_to_http_status(RateLimitException("")) == 429
        assert exception_to_http_status(DatabaseException("")) == 503

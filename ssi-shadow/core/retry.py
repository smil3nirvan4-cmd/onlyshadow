"""
S.S.I. SHADOW - Retry Logic with Exponential Backoff
Enterprise-grade retry decorator for async functions.
"""

import asyncio
import logging
import random
import time
from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    List,
    Awaitable
)
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .exceptions import (
    SSIShadowException,
    is_retryable_exception,
    get_retry_after,
    RateLimitException,
    CircuitBreakerOpenException
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryStrategy(Enum):
    """Retry backoff strategies."""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"
    FIBONACCI = "fibonacci"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    
    # Basic settings
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    
    # Backoff settings
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    exponential_base: float = 2.0
    jitter_factor: float = 0.5  # 0 to 1
    
    # Exception handling
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    non_retryable_exceptions: Tuple[Type[Exception], ...] = ()
    
    # Callbacks
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
    on_success: Optional[Callable[[int], None]] = None
    on_failure: Optional[Callable[[int, Exception], None]] = None
    
    # Logging
    log_retries: bool = True
    log_level: int = logging.WARNING


@dataclass
class RetryStats:
    """Statistics for a retry operation."""
    
    function_name: str
    attempts: int = 0
    successful: bool = False
    total_delay: float = 0.0
    last_exception: Optional[Exception] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    @property
    def duration(self) -> float:
        """Total duration in seconds."""
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()


class RetryExhausted(SSIShadowException):
    """All retry attempts exhausted."""
    
    def __init__(
        self,
        function_name: str,
        attempts: int,
        last_exception: Exception,
        **kwargs
    ):
        super().__init__(
            message=f"Retry exhausted for '{function_name}' after {attempts} attempts",
            error_code="RETRY_001",
            **kwargs
        )
        self.details["function_name"] = function_name
        self.details["attempts"] = attempts
        self.details["last_exception_type"] = type(last_exception).__name__
        self.details["last_exception_message"] = str(last_exception)
        self.last_exception = last_exception


def calculate_delay(
    attempt: int,
    config: RetryConfig,
    exception: Optional[Exception] = None
) -> float:
    """
    Calculate delay before next retry attempt.
    
    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration
        exception: Exception that triggered the retry
    
    Returns:
        Delay in seconds
    """
    # Check if exception specifies retry-after
    if exception:
        retry_after = get_retry_after(exception)
        if retry_after:
            return min(retry_after, config.max_delay)
    
    base = config.base_delay
    
    if config.strategy == RetryStrategy.FIXED:
        delay = base
    
    elif config.strategy == RetryStrategy.LINEAR:
        delay = base * (attempt + 1)
    
    elif config.strategy == RetryStrategy.EXPONENTIAL:
        delay = base * (config.exponential_base ** attempt)
    
    elif config.strategy == RetryStrategy.EXPONENTIAL_JITTER:
        exp_delay = base * (config.exponential_base ** attempt)
        jitter = exp_delay * config.jitter_factor * random.random()
        delay = exp_delay + jitter
    
    elif config.strategy == RetryStrategy.FIBONACCI:
        # Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, ...
        fib = [1, 1]
        for _ in range(attempt):
            fib.append(fib[-1] + fib[-2])
        delay = base * fib[min(attempt, len(fib) - 1)]
    
    else:
        delay = base
    
    # Apply max delay cap
    return min(delay, config.max_delay)


def should_retry(
    exception: Exception,
    attempt: int,
    config: RetryConfig
) -> bool:
    """
    Determine if operation should be retried.
    
    Args:
        exception: Exception that occurred
        attempt: Current attempt number
        config: Retry configuration
    
    Returns:
        True if should retry, False otherwise
    """
    # Check max retries
    if attempt >= config.max_retries:
        return False
    
    # Check non-retryable exceptions first
    if config.non_retryable_exceptions:
        if isinstance(exception, config.non_retryable_exceptions):
            return False
    
    # Check circuit breaker - don't retry if circuit is open
    if isinstance(exception, CircuitBreakerOpenException):
        return False
    
    # Check if exception is retryable
    if isinstance(exception, config.retryable_exceptions):
        return True
    
    # Check SSIShadowException retryable flag
    if isinstance(exception, SSIShadowException):
        return exception.is_retryable
    
    # Check common retryable exceptions
    return is_retryable_exception(exception)


def retry_async(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    strategy: RetryStrategy = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    on_success: Optional[Callable[[int], None]] = None,
    on_failure: Optional[Callable[[int, Exception], None]] = None,
    non_retryable: Tuple[Type[Exception], ...] = (),
    log_retries: bool = True
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator for retrying async functions with exponential backoff.
    
    Args:
        exceptions: Tuple of exceptions to retry on
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter
        strategy: Retry strategy (overrides jitter if set)
        on_retry: Callback called on each retry
        on_success: Callback called on success
        on_failure: Callback called when all retries exhausted
        non_retryable: Exceptions that should never be retried
        log_retries: Whether to log retry attempts
    
    Returns:
        Decorated function
    
    Example:
        @retry_async(
            exceptions=(ConnectionError, TimeoutError),
            max_retries=3,
            base_delay=2.0
        )
        async def fetch_data():
            return await client.get("/data")
    """
    # Determine strategy
    if strategy is None:
        strategy = RetryStrategy.EXPONENTIAL_JITTER if jitter else RetryStrategy.EXPONENTIAL
    
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        strategy=strategy,
        exponential_base=exponential_base,
        jitter_factor=0.5 if jitter else 0,
        retryable_exceptions=exceptions,
        non_retryable_exceptions=non_retryable,
        on_retry=on_retry,
        on_success=on_success,
        on_failure=on_failure,
        log_retries=log_retries
    )
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            stats = RetryStats(function_name=func.__name__)
            last_exception: Optional[Exception] = None
            
            for attempt in range(config.max_retries + 1):
                stats.attempts = attempt + 1
                
                try:
                    result = await func(*args, **kwargs)
                    
                    # Success
                    stats.successful = True
                    stats.completed_at = datetime.utcnow()
                    
                    if config.on_success:
                        config.on_success(attempt)
                    
                    if config.log_retries and attempt > 0:
                        logger.info(
                            f"Retry succeeded for {func.__name__} on attempt {attempt + 1}"
                        )
                    
                    return result
                
                except Exception as e:
                    last_exception = e
                    stats.last_exception = e
                    
                    # Check if we should retry
                    if not should_retry(e, attempt, config):
                        raise
                    
                    # Calculate delay
                    delay = calculate_delay(attempt, config, e)
                    stats.total_delay += delay
                    
                    # Log retry
                    if config.log_retries:
                        logger.log(
                            config.log_level,
                            f"Retry {attempt + 1}/{config.max_retries} for {func.__name__} "
                            f"after {delay:.2f}s due to {type(e).__name__}: {e}"
                        )
                    
                    # Call on_retry callback
                    if config.on_retry:
                        try:
                            config.on_retry(attempt, e, delay)
                        except Exception as callback_error:
                            logger.warning(f"on_retry callback failed: {callback_error}")
                    
                    # Wait before retry
                    await asyncio.sleep(delay)
            
            # All retries exhausted
            stats.completed_at = datetime.utcnow()
            
            if config.on_failure:
                try:
                    config.on_failure(stats.attempts, last_exception)
                except Exception as callback_error:
                    logger.warning(f"on_failure callback failed: {callback_error}")
            
            # Raise RetryExhausted with the last exception
            raise RetryExhausted(
                function_name=func.__name__,
                attempts=stats.attempts,
                last_exception=last_exception
            ) from last_exception
        
        # Attach stats method
        wrapper.get_retry_config = lambda: config
        return wrapper
    
    return decorator


def retry_sync(
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
    log_retries: bool = True
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying synchronous functions with exponential backoff.
    
    Same parameters as retry_async but for sync functions.
    """
    strategy = RetryStrategy.EXPONENTIAL_JITTER if jitter else RetryStrategy.EXPONENTIAL
    
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        strategy=strategy,
        exponential_base=exponential_base,
        jitter_factor=0.5 if jitter else 0,
        retryable_exceptions=exceptions,
        on_retry=on_retry,
        log_retries=log_retries
    )
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                
                except Exception as e:
                    last_exception = e
                    
                    if not should_retry(e, attempt, config):
                        raise
                    
                    delay = calculate_delay(attempt, config, e)
                    
                    if config.log_retries:
                        logger.warning(
                            f"Retry {attempt + 1}/{config.max_retries} for {func.__name__} "
                            f"after {delay:.2f}s due to {type(e).__name__}: {e}"
                        )
                    
                    if config.on_retry:
                        try:
                            config.on_retry(attempt, e, delay)
                        except Exception:
                            pass
                    
                    time.sleep(delay)
            
            raise RetryExhausted(
                function_name=func.__name__,
                attempts=config.max_retries + 1,
                last_exception=last_exception
            ) from last_exception
        
        return wrapper
    
    return decorator


class RetryManager:
    """
    Context manager for retry operations with manual control.
    
    Example:
        async with RetryManager(max_retries=3) as retry:
            async for attempt in retry:
                try:
                    result = await risky_operation()
                    break
                except Exception as e:
                    await attempt.retry(e)
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_JITTER
    ):
        self.config = RetryConfig(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            strategy=strategy,
            retryable_exceptions=exceptions
        )
        self._attempt = 0
        self._last_exception: Optional[Exception] = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False
    
    def __aiter__(self):
        return self
    
    async def __anext__(self) -> 'RetryAttempt':
        if self._attempt > self.config.max_retries:
            if self._last_exception:
                raise RetryExhausted(
                    function_name="RetryManager",
                    attempts=self._attempt,
                    last_exception=self._last_exception
                ) from self._last_exception
            raise StopAsyncIteration
        
        attempt = RetryAttempt(self, self._attempt)
        self._attempt += 1
        return attempt


class RetryAttempt:
    """Represents a single retry attempt."""
    
    def __init__(self, manager: RetryManager, attempt_number: int):
        self._manager = manager
        self.attempt_number = attempt_number
    
    async def retry(self, exception: Exception):
        """
        Signal that this attempt failed and should be retried.
        
        Args:
            exception: The exception that caused the failure
        """
        self._manager._last_exception = exception
        
        if not should_retry(exception, self.attempt_number, self._manager.config):
            raise exception
        
        delay = calculate_delay(self.attempt_number, self._manager.config, exception)
        
        logger.warning(
            f"Retry attempt {self.attempt_number + 1}/{self._manager.config.max_retries} "
            f"after {delay:.2f}s due to {type(exception).__name__}"
        )
        
        await asyncio.sleep(delay)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def retry_operation(
    operation: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    **kwargs
) -> T:
    """
    Retry an async operation without using a decorator.
    
    Args:
        operation: Async function to retry
        *args: Arguments to pass to operation
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        exceptions: Exceptions to retry on
        **kwargs: Keyword arguments to pass to operation
    
    Returns:
        Result of the operation
    
    Example:
        result = await retry_operation(
            client.fetch,
            "/api/data",
            max_retries=3
        )
    """
    @retry_async(
        exceptions=exceptions,
        max_retries=max_retries,
        base_delay=base_delay
    )
    async def _wrapped():
        return await operation(*args, **kwargs)
    
    return await _wrapped()


def with_timeout_and_retry(
    timeout: float,
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator that combines timeout and retry logic.
    
    Args:
        timeout: Timeout in seconds for each attempt
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        exceptions: Exceptions to retry on
    
    Returns:
        Decorated function
    
    Example:
        @with_timeout_and_retry(timeout=10, max_retries=3)
        async def slow_operation():
            ...
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @retry_async(
            exceptions=exceptions + (asyncio.TimeoutError,),
            max_retries=max_retries,
            base_delay=base_delay
        )
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=timeout
            )
        
        return wrapper
    
    return decorator


# =============================================================================
# PREBUILT CONFIGURATIONS
# =============================================================================

# Configuration for API calls
API_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    strategy=RetryStrategy.EXPONENTIAL_JITTER,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
    )
)

# Configuration for database operations
DB_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=0.5,
    max_delay=10.0,
    strategy=RetryStrategy.EXPONENTIAL,
)

# Configuration for cache operations
CACHE_RETRY_CONFIG = RetryConfig(
    max_retries=2,
    base_delay=0.1,
    max_delay=1.0,
    strategy=RetryStrategy.FIXED,
)

# Configuration for critical operations (more aggressive)
CRITICAL_RETRY_CONFIG = RetryConfig(
    max_retries=10,
    base_delay=1.0,
    max_delay=120.0,
    strategy=RetryStrategy.EXPONENTIAL_JITTER,
)


# Convenience decorators with preset configs
def retry_api_call(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator with API retry configuration."""
    return retry_async(
        max_retries=API_RETRY_CONFIG.max_retries,
        base_delay=API_RETRY_CONFIG.base_delay,
        max_delay=API_RETRY_CONFIG.max_delay,
        exceptions=(ConnectionError, TimeoutError, OSError)
    )(func)


def retry_db_operation(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator with database retry configuration."""
    return retry_async(
        max_retries=DB_RETRY_CONFIG.max_retries,
        base_delay=DB_RETRY_CONFIG.base_delay,
        max_delay=DB_RETRY_CONFIG.max_delay,
        jitter=False
    )(func)


def retry_cache_operation(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator with cache retry configuration."""
    return retry_async(
        max_retries=CACHE_RETRY_CONFIG.max_retries,
        base_delay=CACHE_RETRY_CONFIG.base_delay,
        max_delay=CACHE_RETRY_CONFIG.max_delay,
        jitter=False
    )(func)

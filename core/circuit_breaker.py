"""
S.S.I. SHADOW - Circuit Breaker Pattern Implementation
Prevents cascading failures by breaking circuits to failing services.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    Type,
    TypeVar,
    Union
)
from threading import Lock
import json

from .exceptions import CircuitBreakerOpenException

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Circuit is broken, requests are blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitStats:
    """Statistics for circuit breaker."""
    
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rejected_requests": self.rejected_requests,
            "failure_rate": round(self.failure_rate, 4),
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None
        }


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    
    # Failure thresholds
    failure_threshold: int = 5  # Number of failures to open circuit
    failure_rate_threshold: float = 0.5  # Failure rate to open circuit (0-1)
    
    # Recovery settings
    recovery_timeout: float = 30.0  # Seconds to wait before trying half-open
    half_open_max_calls: int = 3  # Successful calls needed to close circuit
    
    # Sliding window for failure rate calculation
    sliding_window_size: int = 10  # Number of calls to consider
    
    # Exceptions
    excluded_exceptions: Set[Type[Exception]] = field(default_factory=set)
    included_exceptions: Set[Type[Exception]] = field(default_factory=set)
    
    # Callbacks
    on_open: Optional[Callable[['CircuitBreaker'], None]] = None
    on_close: Optional[Callable[['CircuitBreaker'], None]] = None
    on_half_open: Optional[Callable[['CircuitBreaker'], None]] = None
    
    # Fallback
    fallback: Optional[Callable[..., Any]] = None


class CircuitBreaker:
    """
    Circuit Breaker implementation for fault tolerance.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing if service recovered
    
    Example:
        breaker = CircuitBreaker(name="external_api", failure_threshold=5)
        
        @breaker.protect
        async def call_external_api():
            return await client.request()
        
        # Or manually:
        result = await breaker.call(lambda: client.request())
    """
    
    # Registry of all circuit breakers
    _registry: Dict[str, 'CircuitBreaker'] = {}
    _registry_lock = Lock()
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        failure_rate_threshold: float = 0.5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        sliding_window_size: int = 10,
        excluded_exceptions: Optional[Set[Type[Exception]]] = None,
        included_exceptions: Optional[Set[Type[Exception]]] = None,
        fallback: Optional[Callable[..., Any]] = None,
        on_open: Optional[Callable[['CircuitBreaker'], None]] = None,
        on_close: Optional[Callable[['CircuitBreaker'], None]] = None,
        on_half_open: Optional[Callable[['CircuitBreaker'], None]] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Unique name for this circuit breaker
            failure_threshold: Number of consecutive failures to open circuit
            failure_rate_threshold: Failure rate threshold (0-1) to open circuit
            recovery_timeout: Seconds to wait before testing recovery
            half_open_max_calls: Successful calls needed to close circuit
            sliding_window_size: Window size for failure rate calculation
            excluded_exceptions: Exceptions that don't count as failures
            included_exceptions: Only these exceptions count as failures (if set)
            fallback: Fallback function when circuit is open
            on_open: Callback when circuit opens
            on_close: Callback when circuit closes
            on_half_open: Callback when circuit enters half-open state
        """
        self.name = name
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            failure_rate_threshold=failure_rate_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            sliding_window_size=sliding_window_size,
            excluded_exceptions=excluded_exceptions or set(),
            included_exceptions=included_exceptions or set(),
            fallback=fallback,
            on_open=on_open,
            on_close=on_close,
            on_half_open=on_half_open
        )
        
        # State
        self._state = CircuitState.CLOSED
        self._state_lock = asyncio.Lock()
        
        # Statistics
        self.stats = CircuitStats()
        
        # Sliding window for recent calls
        self._call_results: deque = deque(maxlen=sliding_window_size)
        
        # Timing
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        
        # Half-open state tracking
        self._half_open_successes = 0
        
        # Register this circuit breaker
        with self._registry_lock:
            self._registry[name] = self
    
    @classmethod
    def get(cls, name: str) -> Optional['CircuitBreaker']:
        """Get circuit breaker by name."""
        return cls._registry.get(name)
    
    @classmethod
    def get_all(cls) -> Dict[str, 'CircuitBreaker']:
        """Get all registered circuit breakers."""
        return dict(cls._registry)
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN
    
    def _should_count_failure(self, exception: Exception) -> bool:
        """Check if exception should count as a failure."""
        exc_type = type(exception)
        
        # If included_exceptions is set, only count those
        if self.config.included_exceptions:
            return exc_type in self.config.included_exceptions
        
        # Otherwise, count all except excluded
        return exc_type not in self.config.excluded_exceptions
    
    def _should_try_reset(self) -> bool:
        """Check if we should try to reset from open state."""
        if self._opened_at is None:
            return True
        
        elapsed = time.monotonic() - self._opened_at
        return elapsed >= self.config.recovery_timeout
    
    def _calculate_window_failure_rate(self) -> float:
        """Calculate failure rate from sliding window."""
        if not self._call_results:
            return 0.0
        
        failures = sum(1 for success in self._call_results if not success)
        return failures / len(self._call_results)
    
    async def _transition_to(self, new_state: CircuitState):
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        
        # Log state change
        change = {
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.stats.state_changes.append(change)
        
        logger.info(
            f"Circuit breaker '{self.name}' state changed: {old_state.value} -> {new_state.value}"
        )
        
        # Call callbacks
        if new_state == CircuitState.OPEN and self.config.on_open:
            try:
                self.config.on_open(self)
            except Exception as e:
                logger.warning(f"on_open callback failed: {e}")
        
        elif new_state == CircuitState.CLOSED and self.config.on_close:
            try:
                self.config.on_close(self)
            except Exception as e:
                logger.warning(f"on_close callback failed: {e}")
        
        elif new_state == CircuitState.HALF_OPEN and self.config.on_half_open:
            try:
                self.config.on_half_open(self)
            except Exception as e:
                logger.warning(f"on_half_open callback failed: {e}")
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._state_lock:
            self.stats.total_requests += 1
            self.stats.successful_requests += 1
            self.stats.consecutive_successes += 1
            self.stats.consecutive_failures = 0
            self.stats.last_success_time = datetime.utcnow()
            
            self._call_results.append(True)
            
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                
                if self._half_open_successes >= self.config.half_open_max_calls:
                    # Recovery successful, close circuit
                    await self._transition_to(CircuitState.CLOSED)
                    self._half_open_successes = 0
    
    async def _on_failure(self, exception: Exception):
        """Handle failed call."""
        if not self._should_count_failure(exception):
            return
        
        async with self._state_lock:
            self.stats.total_requests += 1
            self.stats.failed_requests += 1
            self.stats.consecutive_failures += 1
            self.stats.consecutive_successes = 0
            self.stats.last_failure_time = datetime.utcnow()
            
            self._last_failure_time = time.monotonic()
            self._call_results.append(False)
            
            if self._state == CircuitState.HALF_OPEN:
                # Failure during half-open, go back to open
                await self._transition_to(CircuitState.OPEN)
                self._opened_at = time.monotonic()
                self._half_open_successes = 0
            
            elif self._state == CircuitState.CLOSED:
                # Check if we should open the circuit
                should_open = (
                    self.stats.consecutive_failures >= self.config.failure_threshold or
                    self._calculate_window_failure_rate() >= self.config.failure_rate_threshold
                )
                
                if should_open:
                    await self._transition_to(CircuitState.OPEN)
                    self._opened_at = time.monotonic()
    
    async def _check_state(self):
        """Check and potentially update state before a call."""
        async with self._state_lock:
            if self._state == CircuitState.OPEN:
                if self._should_try_reset():
                    await self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_successes = 0
                else:
                    # Still open, reject request
                    self.stats.rejected_requests += 1
                    raise CircuitBreakerOpenException(
                        service_name=self.name,
                        retry_after=int(
                            self.config.recovery_timeout - 
                            (time.monotonic() - (self._opened_at or 0))
                        )
                    )
    
    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        **kwargs
    ) -> T:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function
        
        Returns:
            Result of the function
        
        Raises:
            CircuitBreakerOpenException: If circuit is open
        """
        # Check if we can proceed
        await self._check_state()
        
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        
        except CircuitBreakerOpenException:
            raise
        
        except Exception as e:
            await self._on_failure(e)
            
            # Try fallback if available
            if self.config.fallback:
                logger.info(f"Using fallback for circuit breaker '{self.name}'")
                return await self.config.fallback(*args, **kwargs)
            
            raise
    
    def protect(
        self,
        func: Callable[..., Awaitable[T]]
    ) -> Callable[..., Awaitable[T]]:
        """
        Decorator to protect an async function with this circuit breaker.
        
        Example:
            breaker = CircuitBreaker(name="api")
            
            @breaker.protect
            async def call_api():
                return await client.request()
        """
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await self.call(func, *args, **kwargs)
        
        return wrapper
    
    async def reset(self):
        """Manually reset the circuit breaker to closed state."""
        async with self._state_lock:
            await self._transition_to(CircuitState.CLOSED)
            self.stats.consecutive_failures = 0
            self._half_open_successes = 0
            self._opened_at = None
            logger.info(f"Circuit breaker '{self.name}' manually reset")
    
    async def force_open(self):
        """Manually force the circuit breaker to open state."""
        async with self._state_lock:
            await self._transition_to(CircuitState.OPEN)
            self._opened_at = time.monotonic()
            logger.info(f"Circuit breaker '{self.name}' manually opened")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the circuit breaker."""
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": self.stats.to_dict(),
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "failure_rate_threshold": self.config.failure_rate_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "half_open_max_calls": self.config.half_open_max_calls
            },
            "time_in_current_state": (
                time.monotonic() - self._opened_at 
                if self._opened_at else None
            )
        }


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    fallback: Optional[Callable[..., Any]] = None,
    **kwargs
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator factory for circuit breaker protection.
    
    Args:
        name: Name for the circuit breaker
        failure_threshold: Failures before opening
        recovery_timeout: Seconds before trying recovery
        fallback: Fallback function when circuit is open
        **kwargs: Additional CircuitBreaker arguments
    
    Returns:
        Decorator function
    
    Example:
        @circuit_breaker(name="payment_api", failure_threshold=3)
        async def process_payment(amount: float):
            return await payment_service.charge(amount)
    """
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        fallback=fallback,
        **kwargs
    )
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        return breaker.protect(func)
    
    return decorator


# =============================================================================
# CIRCUIT BREAKER MANAGER
# =============================================================================

class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers.
    Provides centralized monitoring and control.
    """
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def register(self, breaker: CircuitBreaker):
        """Register a circuit breaker."""
        self._breakers[breaker.name] = breaker
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name) or CircuitBreaker.get(name)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers."""
        all_breakers = {**self._breakers, **CircuitBreaker.get_all()}
        return {name: breaker.get_status() for name, breaker in all_breakers.items()}
    
    def get_open_circuits(self) -> List[str]:
        """Get names of all open circuits."""
        all_breakers = {**self._breakers, **CircuitBreaker.get_all()}
        return [
            name for name, breaker in all_breakers.items()
            if breaker.is_open
        ]
    
    async def reset_all(self):
        """Reset all circuit breakers."""
        all_breakers = {**self._breakers, **CircuitBreaker.get_all()}
        for breaker in all_breakers.values():
            await breaker.reset()
    
    async def reset(self, name: str):
        """Reset a specific circuit breaker."""
        breaker = self.get(name)
        if breaker:
            await breaker.reset()
    
    def create(
        self,
        name: str,
        **kwargs
    ) -> CircuitBreaker:
        """Create and register a new circuit breaker."""
        breaker = CircuitBreaker(name=name, **kwargs)
        self.register(breaker)
        return breaker


# Global manager instance
circuit_manager = CircuitBreakerManager()


# =============================================================================
# PREBUILT CIRCUIT BREAKERS
# =============================================================================

def create_api_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0
) -> CircuitBreaker:
    """Create a circuit breaker configured for API calls."""
    return CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_max_calls=3,
        sliding_window_size=10,
        excluded_exceptions={ValueError, TypeError}  # Don't trip on validation errors
    )


def create_database_circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 60.0
) -> CircuitBreaker:
    """Create a circuit breaker configured for database operations."""
    return CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_max_calls=2,
        sliding_window_size=5
    )


def create_cache_circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    recovery_timeout: float = 10.0
) -> CircuitBreaker:
    """Create a circuit breaker configured for cache operations."""
    return CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        half_open_max_calls=2,
        sliding_window_size=5
    )


# =============================================================================
# HEALTH CHECK INTEGRATION
# =============================================================================

async def get_circuit_breaker_health() -> Dict[str, Any]:
    """
    Get health status of all circuit breakers.
    Suitable for health check endpoints.
    """
    all_breakers = CircuitBreaker.get_all()
    
    open_circuits = [
        name for name, breaker in all_breakers.items()
        if breaker.is_open
    ]
    
    half_open_circuits = [
        name for name, breaker in all_breakers.items()
        if breaker.is_half_open
    ]
    
    status = "healthy"
    if open_circuits:
        status = "degraded"
    
    return {
        "status": status,
        "total_circuits": len(all_breakers),
        "open_circuits": open_circuits,
        "half_open_circuits": half_open_circuits,
        "details": {
            name: {
                "state": breaker.state.value,
                "failure_rate": breaker.stats.failure_rate
            }
            for name, breaker in all_breakers.items()
        }
    }

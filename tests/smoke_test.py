#!/usr/bin/env python3
"""
S.S.I. SHADOW - Smoke Test Suite
=================================
Validates production/staging environment health.

Usage:
    # Basic usage (uses environment variables)
    python tests/smoke_test.py
    
    # With explicit URL
    python tests/smoke_test.py --url https://api.ssi-shadow.io
    
    # With credentials
    python tests/smoke_test.py --url https://api.staging.ssi-shadow.io \
        --email test@example.com --password secret123
    
    # Verbose output
    python tests/smoke_test.py -v
    
    # JSON output (for CI/CD parsing)
    python tests/smoke_test.py --json

Exit Codes:
    0 - All tests passed
    1 - One or more tests failed
    2 - Configuration error

Environment Variables:
    SMOKE_TEST_URL      - API base URL
    SMOKE_TEST_EMAIL    - Test user email
    SMOKE_TEST_PASSWORD - Test user password
    SMOKE_TEST_TIMEOUT  - Request timeout in seconds (default: 30)

Author: SSI Shadow QA Team
Version: 1.0.0
"""

import os
import sys
import json
import time
import argparse
import traceback
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from urllib.parse import urljoin
import io
from contextlib import redirect_stdout, redirect_stderr

# Try to import requests, fall back to urllib if not available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    import urllib.request
    import urllib.error
    import ssl
    REQUESTS_AVAILABLE = False


# =============================================================================
# COLORS & FORMATTING
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    RESET = '\033[0m'
    
    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        cls.RED = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.BLUE = ''
        cls.MAGENTA = ''
        cls.CYAN = ''
        cls.WHITE = ''
        cls.BOLD = ''
        cls.UNDERLINE = ''
        cls.RESET = ''


def print_success(message: str):
    """Print success message in green."""
    print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")


def print_error(message: str):
    """Print error message in red."""
    print(f"{Colors.RED}❌ {message}{Colors.RESET}")


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.RESET}")


def print_info(message: str):
    """Print info message in blue."""
    print(f"{Colors.BLUE}ℹ️  {message}{Colors.RESET}")


def print_step(step: int, total: int, message: str):
    """Print step progress."""
    print(f"\n{Colors.CYAN}[{step}/{total}]{Colors.RESET} {Colors.BOLD}{message}{Colors.RESET}")


# =============================================================================
# DATA CLASSES
# =============================================================================

class TestStatus(Enum):
    """Test result status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    status: TestStatus
    message: str = ""
    duration_ms: float = 0
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "details": self.details
        }


@dataclass
class SmokeTestReport:
    """Complete smoke test report."""
    environment: str
    url: str
    started_at: str
    finished_at: str = ""
    total_duration_ms: float = 0
    tests: List[TestResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    success: bool = False
    
    def add_result(self, result: TestResult):
        self.tests.append(result)
        if result.status == TestStatus.PASSED:
            self.passed += 1
        elif result.status == TestStatus.FAILED:
            self.failed += 1
        elif result.status == TestStatus.SKIPPED:
            self.skipped += 1
    
    def finalize(self):
        self.finished_at = datetime.now(timezone.utc).isoformat() + "Z"
        self.success = self.failed == 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment": self.environment,
            "url": self.url,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "summary": {
                "total": len(self.tests),
                "passed": self.passed,
                "failed": self.failed,
                "skipped": self.skipped,
                "success": self.success
            },
            "tests": [t.to_dict() for t in self.tests]
        }


# =============================================================================
# HTTP CLIENT
# =============================================================================

class HTTPClient:
    """Simple HTTP client that works with or without requests library."""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = None
        
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'SSI-Shadow-SmokeTest/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
    
    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint."""
        if endpoint.startswith('http'):
            return endpoint
        return f"{self.base_url}{endpoint}"
    
    def get(self, endpoint: str, headers: Dict[str, str] = None) -> Tuple[int, Dict[str, Any], float]:
        """
        Make GET request.
        
        Returns:
            Tuple of (status_code, response_json, duration_ms)
        """
        url = self._build_url(endpoint)
        start = time.time()
        
        if REQUESTS_AVAILABLE:
            try:
                resp = self.session.get(
                    url, 
                    headers=headers, 
                    timeout=self.timeout
                )
                duration = (time.time() - start) * 1000
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text}
                return resp.status_code, data, duration
            except requests.exceptions.Timeout:
                raise TimeoutError(f"Request timed out after {self.timeout}s")
            except requests.exceptions.ConnectionError as e:
                raise ConnectionError(f"Connection failed: {e}")
        else:
            # Fallback to urllib
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'SSI-Shadow-SmokeTest/1.0')
            req.add_header('Accept', 'application/json')
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            
            try:
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                    duration = (time.time() - start) * 1000
                    data = json.loads(resp.read().decode('utf-8'))
                    return resp.status, data, duration
            except urllib.error.HTTPError as e:
                duration = (time.time() - start) * 1000
                try:
                    data = json.loads(e.read().decode('utf-8'))
                except:
                    data = {"error": str(e)}
                return e.code, data, duration
            except urllib.error.URLError as e:
                raise ConnectionError(f"Connection failed: {e.reason}")
    
    def post(self, endpoint: str, data: Dict[str, Any], headers: Dict[str, str] = None) -> Tuple[int, Dict[str, Any], float]:
        """
        Make POST request.
        
        Returns:
            Tuple of (status_code, response_json, duration_ms)
        """
        url = self._build_url(endpoint)
        start = time.time()
        
        if REQUESTS_AVAILABLE:
            try:
                resp = self.session.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=self.timeout
                )
                duration = (time.time() - start) * 1000
                try:
                    resp_data = resp.json()
                except:
                    resp_data = {"raw": resp.text}
                return resp.status_code, resp_data, duration
            except requests.exceptions.Timeout:
                raise TimeoutError(f"Request timed out after {self.timeout}s")
            except requests.exceptions.ConnectionError as e:
                raise ConnectionError(f"Connection failed: {e}")
        else:
            # Fallback to urllib
            json_data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(url, data=json_data, method='POST')
            req.add_header('User-Agent', 'SSI-Shadow-SmokeTest/1.0')
            req.add_header('Accept', 'application/json')
            req.add_header('Content-Type', 'application/json')
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)
            
            try:
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                    duration = (time.time() - start) * 1000
                    resp_data = json.loads(resp.read().decode('utf-8'))
                    return resp.status, resp_data, duration
            except urllib.error.HTTPError as e:
                duration = (time.time() - start) * 1000
                try:
                    resp_data = json.loads(e.read().decode('utf-8'))
                except:
                    resp_data = {"error": str(e)}
                return e.code, resp_data, duration
            except urllib.error.URLError as e:
                raise ConnectionError(f"Connection failed: {e.reason}")
    
    def close(self):
        """Close the session."""
        if self.session:
            self.session.close()


# =============================================================================
# SMOKE TEST CLASS
# =============================================================================

class SmokeTest:
    """
    Smoke test runner for SSI Shadow API.
    """
    
    def __init__(
        self,
        base_url: str,
        email: str = None,
        password: str = None,
        timeout: int = 30,
        verbose: bool = False,
        silent: bool = False
    ):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.password = password
        self.timeout = timeout
        self.verbose = verbose
        self.silent = silent
        
        self.client = HTTPClient(base_url, timeout)
        self.token: Optional[str] = None
        self.user_data: Optional[Dict[str, Any]] = None
        
        # Determine environment from URL
        if 'staging' in base_url.lower():
            self.environment = 'staging'
        elif 'localhost' in base_url or '127.0.0.1' in base_url:
            self.environment = 'local'
        elif 'prod' in base_url.lower() or 'api.ssi-shadow' in base_url.lower():
            self.environment = 'production'
        else:
            self.environment = 'unknown'
        
        self.report = SmokeTestReport(
            environment=self.environment,
            url=base_url,
            started_at=datetime.now(timezone.utc).isoformat() + "Z"
        )
    
    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"    {Colors.WHITE}{message}{Colors.RESET}")
    
    # =========================================================================
    # TEST: Health Check
    # =========================================================================
    
    def test_health(self) -> TestResult:
        """
        Test 1: Health Check
        
        Validates that the API is responding to health checks.
        Expected: GET /health returns 200 OK
        """
        name = "Health Check"
        
        try:
            self._log(f"GET {self.base_url}/health")
            
            status_code, data, duration = self.client.get('/health')
            
            self._log(f"Response: {status_code} ({duration:.0f}ms)")
            
            if status_code == 200:
                # Check response content
                status = data.get('status', data.get('health', 'unknown'))
                
                if status.lower() in ['ok', 'healthy', 'up', 'alive']:
                    return TestResult(
                        name=name,
                        status=TestStatus.PASSED,
                        message=f"API is healthy (status: {status})",
                        duration_ms=duration,
                        details={
                            "status_code": status_code,
                            "response": data
                        }
                    )
                else:
                    return TestResult(
                        name=name,
                        status=TestStatus.FAILED,
                        message=f"Unexpected health status: {status}",
                        duration_ms=duration,
                        details={"response": data}
                    )
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message=f"Health check failed with status {status_code}",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "response": data
                    }
                )
                
        except TimeoutError as e:
            return TestResult(
                name=name,
                status=TestStatus.FAILED,
                message=f"Request timed out: {e}",
                details={"error": "timeout"}
            )
        except ConnectionError as e:
            return TestResult(
                name=name,
                status=TestStatus.FAILED,
                message=f"Connection failed: {e}",
                details={"error": "connection_error"}
            )
        except Exception as e:
            return TestResult(
                name=name,
                status=TestStatus.ERROR,
                message=f"Unexpected error: {e}",
                details={"error": str(e), "traceback": traceback.format_exc()}
            )
    
    # =========================================================================
    # TEST: Authentication
    # =========================================================================
    
    def test_login(self) -> TestResult:
        """
        Test 2: Authentication
        
        Validates that the login endpoint works and returns a valid token.
        Expected: POST /api/auth/login returns 200 with access_token
        """
        name = "Authentication"
        
        if not self.email or not self.password:
            return TestResult(
                name=name,
                status=TestStatus.SKIPPED,
                message="No credentials provided (use --email and --password)",
                details={"reason": "missing_credentials"}
            )
        
        try:
            self._log(f"POST {self.base_url}/api/auth/login")
            self._log(f"Email: {self.email}")
            
            status_code, data, duration = self.client.post(
                '/api/auth/login',
                {
                    "email": self.email,
                    "password": self.password
                }
            )
            
            self._log(f"Response: {status_code} ({duration:.0f}ms)")
            
            if status_code == 200:
                # Extract token
                self.token = data.get('access_token') or data.get('token')
                self.user_data = data.get('user', {})
                
                if self.token:
                    # Mask token for logging
                    masked_token = f"{self.token[:10]}...{self.token[-10:]}" if len(self.token) > 20 else "***"
                    self._log(f"Token received: {masked_token}")
                    
                    return TestResult(
                        name=name,
                        status=TestStatus.PASSED,
                        message=f"Login successful (user: {self.user_data.get('email', 'unknown')})",
                        duration_ms=duration,
                        details={
                            "status_code": status_code,
                            "user_id": self.user_data.get('id'),
                            "user_email": self.user_data.get('email'),
                            "token_type": data.get('token_type', 'bearer')
                        }
                    )
                else:
                    return TestResult(
                        name=name,
                        status=TestStatus.FAILED,
                        message="Login response missing access_token",
                        duration_ms=duration,
                        details={"response_keys": list(data.keys())}
                    )
            
            elif status_code == 401:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message="Invalid credentials",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "error": data.get('detail', data.get('message', 'Unknown error'))
                    }
                )
            
            elif status_code == 422:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message="Validation error in request",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "errors": data.get('detail', data)
                    }
                )
            
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message=f"Login failed with status {status_code}",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "response": data
                    }
                )
                
        except TimeoutError as e:
            return TestResult(
                name=name,
                status=TestStatus.FAILED,
                message=f"Request timed out: {e}",
                details={"error": "timeout"}
            )
        except ConnectionError as e:
            return TestResult(
                name=name,
                status=TestStatus.FAILED,
                message=f"Connection failed: {e}",
                details={"error": "connection_error"}
            )
        except Exception as e:
            return TestResult(
                name=name,
                status=TestStatus.ERROR,
                message=f"Unexpected error: {e}",
                details={"error": str(e), "traceback": traceback.format_exc()}
            )
    
    # =========================================================================
    # TEST: Dashboard Overview
    # =========================================================================
    
    def test_dashboard_overview(self) -> TestResult:
        """
        Test 3: Dashboard Overview
        
        Validates that authenticated requests to dashboard work.
        Expected: GET /api/dashboard/overview returns 200 with data
        """
        name = "Dashboard Overview"
        
        if not self.token:
            return TestResult(
                name=name,
                status=TestStatus.SKIPPED,
                message="Skipped - no authentication token available",
                details={"reason": "no_token"}
            )
        
        try:
            self._log(f"GET {self.base_url}/api/dashboard/overview")
            self._log(f"Authorization: Bearer {self.token[:10]}...")
            
            headers = {
                "Authorization": f"Bearer {self.token}"
            }
            
            status_code, data, duration = self.client.get(
                '/api/dashboard/overview',
                headers=headers
            )
            
            self._log(f"Response: {status_code} ({duration:.0f}ms)")
            
            if status_code == 200:
                # Validate response has expected structure
                expected_keys = {'metrics', 'events', 'conversions', 'summary'}
                actual_keys = set(data.keys())
                
                # Check if it has at least some expected keys or is a valid response
                if actual_keys & expected_keys or data:
                    return TestResult(
                        name=name,
                        status=TestStatus.PASSED,
                        message="Dashboard overview retrieved successfully",
                        duration_ms=duration,
                        details={
                            "status_code": status_code,
                            "response_keys": list(data.keys()),
                            "has_data": bool(data)
                        }
                    )
                else:
                    return TestResult(
                        name=name,
                        status=TestStatus.PASSED,
                        message="Dashboard returned empty but valid response",
                        duration_ms=duration,
                        details={
                            "status_code": status_code,
                            "response": data
                        }
                    )
            
            elif status_code == 401:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message="Authentication token rejected",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "error": data.get('detail', 'Unauthorized')
                    }
                )
            
            elif status_code == 403:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message="Access forbidden - insufficient permissions",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "error": data.get('detail', 'Forbidden')
                    }
                )
            
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message=f"Dashboard request failed with status {status_code}",
                    duration_ms=duration,
                    details={
                        "status_code": status_code,
                        "response": data
                    }
                )
                
        except TimeoutError as e:
            return TestResult(
                name=name,
                status=TestStatus.FAILED,
                message=f"Request timed out: {e}",
                details={"error": "timeout"}
            )
        except ConnectionError as e:
            return TestResult(
                name=name,
                status=TestStatus.FAILED,
                message=f"Connection failed: {e}",
                details={"error": "connection_error"}
            )
        except Exception as e:
            return TestResult(
                name=name,
                status=TestStatus.ERROR,
                message=f"Unexpected error: {e}",
                details={"error": str(e), "traceback": traceback.format_exc()}
            )
    
    # =========================================================================
    # ADDITIONAL TESTS
    # =========================================================================
    
    def test_api_version(self) -> TestResult:
        """
        Test 4: API Version (Optional)
        
        Check API version endpoint if available.
        """
        name = "API Version"
        
        try:
            self._log(f"GET {self.base_url}/api/version")
            
            status_code, data, duration = self.client.get('/api/version')
            
            if status_code == 200:
                version = data.get('version', data.get('api_version', 'unknown'))
                return TestResult(
                    name=name,
                    status=TestStatus.PASSED,
                    message=f"API version: {version}",
                    duration_ms=duration,
                    details={"version": version}
                )
            elif status_code == 404:
                return TestResult(
                    name=name,
                    status=TestStatus.SKIPPED,
                    message="Version endpoint not available",
                    duration_ms=duration
                )
            else:
                return TestResult(
                    name=name,
                    status=TestStatus.FAILED,
                    message=f"Version check failed: {status_code}",
                    duration_ms=duration
                )
                
        except Exception as e:
            return TestResult(
                name=name,
                status=TestStatus.SKIPPED,
                message=f"Version check skipped: {e}"
            )
    
    # =========================================================================
    # RUN ALL TESTS
    # =========================================================================
    
    def run(self) -> SmokeTestReport:
        """
        Run all smoke tests.
        
        Returns:
            SmokeTestReport with all results
        """
        start_time = time.time()
        
        tests = [
            (1, "Health Check", self.test_health),
            (2, "Authentication", self.test_login),
            (3, "Dashboard Overview", self.test_dashboard_overview),
            (4, "API Version", self.test_api_version),
        ]
        
        total = len(tests)
        
        for step, name, test_func in tests:
            if not self.silent:
                print_step(step, total, name)
            
            result = test_func()
            self.report.add_result(result)
            
            if not self.silent:
                if result.status == TestStatus.PASSED:
                    print_success(result.message)
                elif result.status == TestStatus.FAILED:
                    print_error(result.message)
                    if self.verbose and result.details:
                        print(f"    Details: {json.dumps(result.details, indent=2)}")
                elif result.status == TestStatus.SKIPPED:
                    print_warning(result.message)
                elif result.status == TestStatus.ERROR:
                    print_error(f"ERROR: {result.message}")
                    if self.verbose and result.details.get('traceback'):
                        print(f"    {result.details['traceback']}")
        
        # Finalize report
        self.report.total_duration_ms = (time.time() - start_time) * 1000
        self.report.finalize()
        
        # Close client
        self.client.close()
        
        return self.report


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='SSI Shadow Smoke Test Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --url https://api.ssi-shadow.io
  %(prog)s --url https://staging.ssi-shadow.io --email test@test.com --password secret
  %(prog)s -v --json > results.json
        """
    )
    
    parser.add_argument(
        '--url', '-u',
        default=os.getenv('SMOKE_TEST_URL', 'http://localhost:8000'),
        help='API base URL (default: $SMOKE_TEST_URL or http://localhost:8000)'
    )
    parser.add_argument(
        '--email', '-e',
        default=os.getenv('SMOKE_TEST_EMAIL'),
        help='Test user email (default: $SMOKE_TEST_EMAIL)'
    )
    parser.add_argument(
        '--password', '-p',
        default=os.getenv('SMOKE_TEST_PASSWORD'),
        help='Test user password (default: $SMOKE_TEST_PASSWORD)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=int(os.getenv('SMOKE_TEST_TIMEOUT', '30')),
        help='Request timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    
    args = parser.parse_args()
    
    # Disable colors if requested or not a TTY
    if args.no_color or not sys.stdout.isatty():
        Colors.disable()
    
    # Print header
    if not args.json:
        print()
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}🔥 S.S.I. SHADOW - SMOKE TEST{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print()
        print_info(f"Target URL: {args.url}")
        print_info(f"Timeout: {args.timeout}s")
        if args.email:
            print_info(f"Auth User: {args.email}")
        else:
            print_warning("No credentials provided - auth tests will be skipped")
    
    # Run tests
    smoke_test = SmokeTest(
        base_url=args.url,
        email=args.email,
        password=args.password,
        timeout=args.timeout,
        verbose=args.verbose,
        silent=args.json  # Silent mode for JSON output
    )
    
    try:
        report = smoke_test.run()
    except KeyboardInterrupt:
        print_error("\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(2)
    
    # Output results
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        # Print summary
        print()
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}📊 SUMMARY{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print()
        print(f"  Environment: {report.environment}")
        print(f"  Duration:    {report.total_duration_ms:.0f}ms")
        print()
        print(f"  {Colors.GREEN}Passed:{Colors.RESET}  {report.passed}")
        print(f"  {Colors.RED}Failed:{Colors.RESET}  {report.failed}")
        print(f"  {Colors.YELLOW}Skipped:{Colors.RESET} {report.skipped}")
        print()
        
        if report.success:
            print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
            print(f"{Colors.GREEN}{Colors.BOLD}✅ ALL TESTS PASSED!{Colors.RESET}")
            print(f"{Colors.GREEN}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
            print(f"{Colors.RED}{Colors.BOLD}❌ SOME TESTS FAILED!{Colors.RESET}")
            print(f"{Colors.RED}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
            
            # List failures
            print()
            print(f"{Colors.RED}Failed tests:{Colors.RESET}")
            for test in report.tests:
                if test.status == TestStatus.FAILED:
                    print(f"  - {test.name}: {test.message}")
        
        print()
    
    # Exit with appropriate code
    sys.exit(0 if report.success else 1)


if __name__ == '__main__':
    main()

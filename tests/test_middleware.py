"""
Tests for security middleware.
"""

from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from micboard.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware


class SecurityHeadersMiddlewareTest(TestCase):
    """Test security headers middleware"""

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SecurityHeadersMiddleware(lambda r: HttpResponse())

    def test_security_headers_added(self):
        """Test that security headers are added to responses"""
        request = self.factory.get("/test/")
        response = self.middleware(request)

        # Check Content Security Policy
        self.assertIn("Content-Security-Policy", response)
        csp = response["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self' 'unsafe-inline' 'unsafe-eval'", csp)
        self.assertIn("connect-src 'self' ws: wss:", csp)

        # Check other security headers
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("Permissions-Policy", response)

        # Check server header is removed
        self.assertNotIn("Server", response)

    def test_csp_allows_django_admin(self):
        """Test that CSP allows Django admin resources"""
        request = self.factory.get("/admin/")
        response = self.middleware(request)

        csp = response["Content-Security-Policy"]
        # Should allow unsafe-inline for Django admin scripts
        self.assertIn("'unsafe-inline'", csp)
        # Should allow unsafe-eval for Django admin
        self.assertIn("'unsafe-eval'", csp)

    def test_csp_allows_websockets(self):
        """Test that CSP allows WebSocket connections"""
        request = self.factory.get("/ws/")
        response = self.middleware(request)

        csp = response["Content-Security-Policy"]
        self.assertIn("ws:", csp)
        self.assertIn("wss:", csp)


class RequestLoggingMiddlewareTest(TestCase):
    """Test request logging middleware"""

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = RequestLoggingMiddleware(lambda r: HttpResponse())

    def test_normal_request_no_logging(self):
        """Test that normal requests don't trigger suspicious logging"""
        request = self.factory.get("/api/receivers/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"

        with patch("micboard.middleware.logger") as mock_logger:
            self.middleware(request)
            # Should not log warnings for normal requests
            mock_logger.warning.assert_not_called()

    @patch("micboard.middleware.logger")
    def test_suspicious_path_logging(self, mock_logger):
        """Test that suspicious paths are logged"""
        request = self.factory.get("/api/receivers/../../../etc/passwd")
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        request.META["HTTP_USER_AGENT"] = "Suspicious Agent"

        self.middleware(request)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        self.assertIn("Suspicious request detected", call_args)
        self.assertIn("../../../etc/passwd", call_args)
        self.assertIn("192.168.1.100", call_args)

    @patch("micboard.middleware.logger")
    def test_suspicious_user_agent_logging(self, mock_logger):
        """Test that suspicious user agents are logged"""
        request = self.factory.get("/api/receivers/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        request.META["HTTP_USER_AGENT"] = "Bad<script>alert('xss')</script>Agent"

        self.middleware(request)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        self.assertIn("Suspicious request detected", call_args)
        self.assertIn("<script", call_args)

    @patch("micboard.middleware.logger")
    def test_sql_injection_logging(self, mock_logger):
        """Test that SQL injection attempts are logged"""
        request = self.factory.post("/api/receivers/", {"name": "'; DROP TABLE users; --"})
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        request.META["HTTP_USER_AGENT"] = "SQL Injector"

        self.middleware(request)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        self.assertIn("Suspicious request detected", call_args)
        self.assertIn("union select", call_args.lower())

    @patch("micboard.middleware.logger")
    def test_code_injection_logging(self, mock_logger):
        """Test that code injection attempts are logged"""
        request = self.factory.get("/api/receivers/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        request.META["HTTP_USER_AGENT"] = "Code Injector"
        request.META["QUERY_STRING"] = "param=eval(console.log('test'))"

        self.middleware(request)

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        self.assertIn("Suspicious request detected", call_args)
        self.assertIn("eval(", call_args)

    @patch("micboard.middleware.logger")
    def test_authentication_failure_logging(self, mock_logger):
        """Test that authentication failures are logged"""

        # Create a mock response with 401 status
        def mock_get_response(request):
            response = HttpResponse()
            response.status_code = 401
            return response

        middleware = RequestLoggingMiddleware(mock_get_response)
        request = self.factory.get("/api/receivers/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        request.META["HTTP_USER_AGENT"] = "Failed Auth"

        middleware(request)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        self.assertIn("Authentication failure", call_args)
        self.assertIn("192.168.1.100", call_args)

    def test_get_client_ip_direct(self):
        """Test _get_client_ip method directly"""
        middleware = RequestLoggingMiddleware(lambda r: HttpResponse())

        # Test REMOTE_ADDR
        request = self.factory.get("/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        self.assertEqual(middleware._get_client_ip(request), "192.168.1.100")

        # Test X-Forwarded-For
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.200"
        self.assertEqual(middleware._get_client_ip(request), "10.0.0.1")

        # Test multiple IPs in X-Forwarded-For
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.200, 172.16.0.1"
        self.assertEqual(middleware._get_client_ip(request), "10.0.0.1")

        # Test no headers
        request.META.pop("HTTP_X_FORWARDED_FOR", None)
        request.META.pop("REMOTE_ADDR", None)
        self.assertEqual(middleware._get_client_ip(request), "Unknown")

    def test_middleware_chaining(self):
        """Test that middleware can be chained together"""

        def mock_view(request):
            return HttpResponse("OK")

        # Chain both middlewares
        security_middleware = SecurityHeadersMiddleware(RequestLoggingMiddleware(mock_view))

        request = self.factory.get("/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        response = security_middleware(request)

        # Should have security headers
        self.assertIn("Content-Security-Policy", response)
        self.assertEqual(response["X-Frame-Options"], "DENY")

        # Should return the view response
        self.assertEqual(response.content.decode(), "OK")

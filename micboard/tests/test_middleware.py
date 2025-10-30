from unittest.mock import MagicMock, patch

from django.http import HttpRequest, HttpResponse
from django.test import TestCase

from micboard.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware


class SecurityHeadersMiddlewareTest(TestCase):
    def setUp(self):
        self.get_response = MagicMock(return_value=HttpResponse("Test"))
        self.middleware = SecurityHeadersMiddleware(self.get_response)
        self.request = HttpRequest()

    def test_security_headers_added(self):
        response = self.middleware(self.request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(
            response["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        self.assertIn("Content-Security-Policy", response)
        self.assertNotIn("Server", response)

    def test_csp_content(self):
        response = self.middleware(self.request)
        csp = response["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self' 'unsafe-inline' 'unsafe-eval'", csp)
        self.assertIn("connect-src 'self' ws: wss:", csp)
        self.assertIn("frame-ancestors 'none'", csp)


class RequestLoggingMiddlewareTest(TestCase):
    def setUp(self):
        self.get_response = MagicMock(return_value=HttpResponse("Test"))
        self.middleware = RequestLoggingMiddleware(self.get_response)
        self.request = HttpRequest()
        self.request.META["REMOTE_ADDR"] = "127.0.0.1"
        self.request.method = "GET"
        self.request.path = "/test/path/"

    @patch("micboard.middleware.logger")
    def test_normal_request_not_logged(self, mock_logger):
        self.middleware(self.request)
        mock_logger.warning.assert_not_called()
        mock_logger.info.assert_not_called()

    @patch("micboard.middleware.logger")
    def test_suspicious_path_logged(self, mock_logger):
        self.request.path = "/test/../../etc/passwd"
        self.middleware(self.request)
        mock_logger.warning.assert_called_once()
        self.assertIn("Suspicious request detected", mock_logger.warning.call_args[0][0])

    @patch("micboard.middleware.logger")
    def test_suspicious_user_agent_logged(self, mock_logger):
        self.request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 <script>alert(1)</script>"
        self.middleware(self.request)
        mock_logger.warning.assert_called_once()
        self.assertIn("Suspicious request detected", mock_logger.warning.call_args[0][0])

    @patch("micboard.middleware.logger")
    def test_auth_failure_logged(self, mock_logger):
        self.get_response.return_value = HttpResponse("Unauthorized", status=401)
        self.middleware(self.request)
        mock_logger.info.assert_called_once()
        self.assertIn("Authentication failure", mock_logger.info.call_args[0][0])

    def test_get_client_ip_x_forwarded_for(self):
        self.request.META["HTTP_X_FORWARDED_FOR"] = "192.168.1.1, 10.0.0.1"
        ip = self.middleware._get_client_ip(self.request)
        self.assertEqual(ip, "192.168.1.1")

    def test_get_client_ip_remote_addr(self):
        # HTTP_X_FORWARDED_FOR is not set
        ip = self.middleware._get_client_ip(self.request)
        self.assertEqual(ip, "127.0.0.1")

    def test_get_client_ip_unknown(self):
        del self.request.META["REMOTE_ADDR"]
        ip = self.middleware._get_client_ip(self.request)
        self.assertEqual(ip, "Unknown")

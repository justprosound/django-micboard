"""
Tests for rate limiting decorators.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from micboard.decorators import get_client_ip, rate_limit_user, rate_limit_view


class RateLimitDecoratorTest(TestCase):
    """Test rate limiting decorators"""

    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()  # Clear cache before each test

    def test_rate_limit_view_under_limit(self):
        """Test that requests under the limit are allowed"""

        @rate_limit_view(max_requests=5, window_seconds=60)
        def test_view(request):  # type: ignore
            return JsonResponse({"status": "ok"})

        # Make requests under the limit
        for _ in range(3):
            request = self.factory.get("/test/")
            request.META["REMOTE_ADDR"] = "192.168.1.100"
            response = test_view(request)
            self.assertEqual(response.status_code, 200)
            import json

            self.assertEqual(json.loads(response.content.decode()), {"status": "ok"})

    def test_rate_limit_view_over_limit(self):
        """Test that requests over the limit are blocked"""

        @rate_limit_view(max_requests=2, window_seconds=60)
        def test_view(request):  # type: ignore
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        # First two requests should succeed
        response1 = test_view(request)
        self.assertEqual(response1.status_code, 200)

        response2 = test_view(request)
        self.assertEqual(response2.status_code, 200)

        # Third request should be rate limited
        response3 = test_view(request)
        self.assertEqual(response3.status_code, 429)
        import json

        data = json.loads(response3.content.decode())
        self.assertIn("Rate limit exceeded", data["error"])
        self.assertIn("retry_after", data)

    def test_rate_limit_view_custom_key_func(self):
        """Test rate limiting with custom key function"""

        def custom_key_func(request):  # type: ignore
            return f"custom_{request.META.get('HTTP_USER_AGENT', 'unknown')}"

        @rate_limit_view(max_requests=1, window_seconds=60, key_func=custom_key_func)
        def test_view(request):
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.META["HTTP_USER_AGENT"] = "test-agent"

        # First request should succeed
        response1 = test_view(request)
        self.assertEqual(response1.status_code, 200)

        # Second request should be rate limited
        response2 = test_view(request)
        self.assertEqual(response2.status_code, 429)

    def test_rate_limit_view_x_forwarded_for(self):
        """Test that X-Forwarded-For header is used for IP detection"""

        @rate_limit_view(max_requests=1, window_seconds=60)
        def test_view(request):
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.100"
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        # Should use the first IP from X-Forwarded-For
        response = test_view(request)
        self.assertEqual(response.status_code, 200)

        # Second request should be rate limited
        response2 = test_view(request)
        self.assertEqual(response2.status_code, 429)

    def test_rate_limit_user_authenticated(self):
        """Test user-based rate limiting for authenticated users"""

        @rate_limit_user(max_requests=1, window_seconds=60)
        def test_view(request):
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.user = type("MockUser", (), {"id": 123, "is_authenticated": True})()  # type: ignore

        # First request should succeed
        response1 = test_view(request)
        self.assertEqual(response1.status_code, 200)

        # Second request should be rate limited
        response2 = test_view(request)
        self.assertEqual(response2.status_code, 429)

    def test_rate_limit_user_anonymous(self):
        """Test user-based rate limiting falls back to IP for anonymous users"""

        @rate_limit_user(max_requests=1, window_seconds=60)
        def test_view(request):
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.user = type("MockUser", (), {"is_authenticated": False})()  # type: ignore
        request.META["REMOTE_ADDR"] = "192.168.1.200"

        # First request should succeed
        response1 = test_view(request)
        self.assertEqual(response1.status_code, 200)

        # Second request should be rate limited
        response2 = test_view(request)
        self.assertEqual(response2.status_code, 429)

    def test_get_client_ip_direct(self):
        """Test get_client_ip function directly"""
        request = self.factory.get("/test/")

        # Test REMOTE_ADDR
        request.META["REMOTE_ADDR"] = "192.168.1.100"
        self.assertEqual(get_client_ip(request), "192.168.1.100")

        # Test X-Forwarded-For
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.200"
        self.assertEqual(get_client_ip(request), "10.0.0.1")

        # Test multiple IPs in X-Forwarded-For
        request.META["HTTP_X_FORWARDED_FOR"] = "10.0.0.1, 192.168.1.200, 172.16.0.1"
        self.assertEqual(get_client_ip(request), "10.0.0.1")

    @patch("micboard.decorators.cache")
    def test_rate_limit_view_cache_error(self, mock_cache):  # type: ignore
        """Test that cache errors don't break the view"""

        # Mock cache to raise an exception
        mock_cache.get.side_effect = Exception("Cache error")
        mock_cache.set.side_effect = Exception("Cache error")

        @rate_limit_view(max_requests=1, window_seconds=60)
        def test_view(request):  # type: ignore
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        # Should still work despite cache errors (falls back to allowing request)
        response = test_view(request)
        self.assertEqual(response.status_code, 200)
        import json

        self.assertEqual(json.loads(response.content.decode()), {"status": "ok"})

    def test_rate_limit_view_window_expiration(self):
        """Test that rate limit window expires correctly"""

        @rate_limit_view(max_requests=1, window_seconds=1)  # Very short window
        def test_view(request):
            return JsonResponse({"status": "ok"})

        request = self.factory.get("/test/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        # First request should succeed
        response1 = test_view(request)
        self.assertEqual(response1.status_code, 200)

        # Second request should be rate limited
        response2 = test_view(request)
        self.assertEqual(response2.status_code, 429)

        # Wait for window to expire (simulate by clearing cache)
        cache.clear()

        # Third request should succeed again
        response3 = test_view(request)
        self.assertEqual(response3.status_code, 200)

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, TestCase
from rest_framework import status

from micboard.api.base_views import APIView, ManufacturerFilterMixin, VersionedAPIView
from micboard.models import Manufacturer, Receiver


# Dummy views for testing APIView dispatch behavior
class DummyAPIView(APIView):
    def get(self, request, *args, **kwargs):
        return HttpResponse("OK", content_type="")


class DummyAPIViewWithContentType(APIView):
    def get(self, request, *args, **kwargs):
        return HttpResponse("OK", content_type="text/html; charset=utf-8")


class APIViewTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.request = self.factory.get("/")

    def test_dispatch_adds_headers(self):
        view = DummyAPIView()
        response = view.dispatch(self.request)

        self.assertEqual(response["X-API-Version"], view.API_VERSION)
        self.assertEqual(response["X-API-Compatible"], "1.0.0")
        self.assertEqual(response["Content-Type"], "application/json")

    def test_dispatch_does_not_overwrite_content_type(self):
        view = DummyAPIViewWithContentType()
        response = view.dispatch(self.request)

        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")

        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")


class ManufacturerFilterMixinTest(TestCase):
    def setUp(self):
        self.mixin = ManufacturerFilterMixin()
        self.request = HttpRequest()
        self.manufacturer = Manufacturer.objects.create(code="shure", name="Shure")
        self.other_manufacturer = Manufacturer.objects.create(code="sennheiser", name="Sennheiser")
        self.receiver1 = Receiver.objects.create(
            name="Receiver 1",
            ip="192.168.1.1",
            manufacturer=self.manufacturer,
            api_device_id="1",
        )
        self.receiver2 = Receiver.objects.create(
            name="Receiver 2",
            ip="192.168.1.2",
            manufacturer=self.other_manufacturer,
            api_device_id="2",
        )

    def test_filter_queryset_by_manufacturer_no_code(self):
        queryset = Receiver.objects.all()
        filtered_queryset, error_response = self.mixin.filter_queryset_by_manufacturer(
            queryset, self.request
        )
        self.assertIsNone(error_response)
        self.assertEqual(filtered_queryset.count(), 2)

    def test_filter_queryset_by_manufacturer_valid_code(self):
        self.request.GET = {"manufacturer": "shure"}
        queryset = Receiver.objects.all()
        filtered_queryset, error_response = self.mixin.filter_queryset_by_manufacturer(
            queryset, self.request
        )
        self.assertIsNone(error_response)
        self.assertEqual(filtered_queryset.count(), 1)
        self.assertEqual(filtered_queryset.first(), self.receiver1)

    def test_filter_queryset_by_manufacturer_invalid_code(self):
        self.request.GET = {"manufacturer": "nonexistent"}
        queryset = Receiver.objects.all()
        filtered_queryset, error_response = self.mixin.filter_queryset_by_manufacturer(
            queryset, self.request
        )
        self.assertIsNone(filtered_queryset)
        self.assertIsNotNone(error_response)
        self.assertEqual(error_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", error_response.data)


class VersionedAPIViewTest(TestCase):
    def setUp(self):
        self.request = HttpRequest()
        self.view = VersionedAPIView()

    def test_get_api_version_from_accept_header(self):
        self.request.META["HTTP_ACCEPT"] = "application/json; version=1.1"
        version = self.view.get_api_version(self.request)
        self.assertEqual(version, "1.1")

    def test_get_api_version_from_query_parameter(self):
        self.request.GET = {"version": "2.0"}
        version = self.view.get_api_version(self.request)
        self.assertEqual(version, "2.0")

    def test_get_api_version_default(self):
        version = self.view.get_api_version(self.request)
        self.assertEqual(version, self.view.API_VERSION)

    def test_get_api_version_invalid_accept_header(self):
        self.request.META["HTTP_ACCEPT"] = "application/json; version"
        version = self.view.get_api_version(self.request)
        self.assertEqual(version, self.view.API_VERSION)

    def test_get_api_version_accept_header_and_query_param(self):
        self.request.META["HTTP_ACCEPT"] = "application/json; version=1.1"
        self.request.GET = {"version": "2.0"}
        version = self.view.get_api_version(self.request)
        # Accept header takes precedence
        self.assertEqual(version, "1.1")

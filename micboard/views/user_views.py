from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from micboard.models import UserView


class RecordUserView(View):
    def post(self, request, *args, **kwargs):
        view_name = request.POST.get("view_name")
        if view_name:
            UserView.objects.update_or_create(
                user=request.user,
                view_name=view_name,
                defaults={"last_accessed": timezone.now()},
            )
            return JsonResponse({"status": "ok"})
        return JsonResponse({"status": "error", "message": "view_name not provided"}, status=400)

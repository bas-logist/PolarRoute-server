from django.http import HttpResponse
from django.template import loader
from django.conf import settings


def frontend_view(request):
    enabled = getattr(settings, "POLARROUTE_FRONTEND_ENABLED", False)
    if enabled:
        template = loader.get_template("frontend/index.html")
    else:
        template = loader.get_template("frontend/unavailable.html")
    return HttpResponse(template.render({}, request))

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("classroom/", include("classroom.urls")),
]

# App file links go through classroom download_* views (auth-checked).
# Keep /media/ available in production too so FileField.url and direct
# paths work on Render's ephemeral disk (first deploy; replace with S3/R2 later).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

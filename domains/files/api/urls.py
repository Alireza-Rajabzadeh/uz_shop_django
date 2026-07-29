from django.urls import path

from .views import FileDetail, FileListCreate, FileOrphanList, FileStatusList, FileVerify


urlpatterns = [
    path("", FileListCreate.as_view()),
    path("statuses", FileStatusList.as_view()),
    path("orphans", FileOrphanList.as_view()),
    path("<uuid:file_id>", FileDetail.as_view()),
    path("<uuid:file_id>/verify", FileVerify.as_view()),
]

import hashlib
import logging
import mimetypes
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import storages
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from domains.files.models import File, FileStatus


logger = logging.getLogger(__name__)


class FileService:
    class Error(Exception):
        def __init__(self, message, *, file=None):
            self.file = file
            super().__init__(message)

    STATUS_PENDING = "pending"
    STATUS_AVAILABLE = "available"
    STATUS_FAILED = "failed"
    STATUS_DELETED = "deleted"
    ORDERING_FIELDS = {
        "created_at",
        "updated_at",
        "original_name",
        "size",
        "file_type",
        "status__name",
    }

    def _storage(self, alias):
        if alias not in settings.FILE_STORAGE_ALIASES:
            raise self.Error(f"Storage alias '{alias}' is not allowed for managed files.")
        try:
            return storages[alias]
        except Exception as exc:
            raise self.Error(f"Storage alias '{alias}' is not configured.") from exc

    def _status(self, name):
        try:
            return FileStatus.objects.get(name=name)
        except FileStatus.DoesNotExist as exc:
            raise self.Error(f"File status '{name}' is not configured.") from exc

    @staticmethod
    def _extension(filename):
        suffix = Path(filename or "").suffix.lower().lstrip(".")
        return "".join(character for character in suffix if character.isalnum())[:50]

    @staticmethod
    def _file_type(content_type):
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type.startswith("text/") or content_type.startswith("application/"):
            return "document"
        return "other"

    @staticmethod
    def _digest(uploaded_file):
        checksum = hashlib.sha256()
        size = 0
        try:
            uploaded_file.seek(0)
            for chunk in uploaded_file.chunks():
                checksum.update(chunk)
                size += len(chunk)
        finally:
            uploaded_file.seek(0)
        return checksum.hexdigest(), size

    def upload(self, uploaded_file, *, storage_alias="default", metadata=None, created_by=None):
        if metadata is not None and not isinstance(metadata, dict):
            raise self.Error("File metadata must be a JSON object.")
        storage = self._storage(storage_alias)
        file_id = uuid.uuid4()
        extension = self._extension(uploaded_file.name)
        content_type = (
            getattr(uploaded_file, "content_type", "")
            or mimetypes.guess_type(uploaded_file.name)[0]
            or "application/octet-stream"
        )
        checksum, size = self._digest(uploaded_file)
        file = File.objects.create(
            id=file_id,
            status=self._status(self.STATUS_PENDING),
            storage_alias=storage_alias,
            object_key=f"files/{file_id}.{extension}" if extension else f"files/{file_id}",
            original_name=Path(uploaded_file.name).name[:255],
            file_type=self._file_type(content_type),
            content_type=content_type[:255],
            extension=extension,
            size=size,
            checksum=checksum,
            metadata=metadata or {},
            created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        )
        saved_key = None
        try:
            saved_key = storage.save(file.object_key, uploaded_file)
            if saved_key != file.object_key:
                file.object_key = saved_key
            file.status = self._status(self.STATUS_AVAILABLE)
            file.save(update_fields=["object_key", "status", "updated_at"])
            return file
        except Exception as exc:
            for key in {saved_key, file.object_key} - {None}:
                try:
                    storage.delete(key)
                except Exception:
                    pass
            file.status = self._status(self.STATUS_FAILED)
            file.save(update_fields=["status", "updated_at"])
            raise self.Error("The file could not be stored.", file=file) from exc

    def url(self, file):
        if file.status.name != self.STATUS_AVAILABLE:
            return None
        try:
            return self._storage(file.storage_alias).url(file.object_key)
        except Exception as exc:
            raise self.Error("The file URL could not be generated.", file=file) from exc

    def exists(self, file):
        try:
            return self._storage(file.storage_alias).exists(file.object_key)
        except Exception as exc:
            raise self.Error("File existence could not be checked.", file=file) from exc

    def verify(self, file):
        with transaction.atomic():
            locked_file = File.objects.select_for_update(of=("self",)).select_related(
                "status"
            ).get(pk=file.pk)
            if locked_file.deleted_at is not None:
                raise self.Error("Deleted files cannot be verified.", file=locked_file)
            storage = self._storage(locked_file.storage_alias)
            valid = False
            try:
                if storage.exists(locked_file.object_key):
                    checksum = hashlib.sha256()
                    size = 0
                    with storage.open(locked_file.object_key, "rb") as stored_file:
                        chunks = getattr(stored_file, "chunks", None)
                        iterator = chunks() if chunks else iter(
                            lambda: stored_file.read(64 * 1024), b""
                        )
                        for chunk in iterator:
                            checksum.update(chunk)
                            size += len(chunk)
                    valid = (
                        size == locked_file.size
                        and checksum.hexdigest() == locked_file.checksum
                    )
            except Exception as exc:
                locked_file.status = self._status(self.STATUS_FAILED)
                locked_file.save(update_fields=["status", "updated_at"])
                raise self.Error(
                    "The stored file could not be verified.", file=locked_file
                ) from exc
            locked_file.status = self._status(
                self.STATUS_AVAILABLE if valid else self.STATUS_FAILED
            )
            locked_file.save(update_fields=["status", "updated_at"])
        file.status = locked_file.status
        file.updated_at = locked_file.updated_at
        return file

    def delete(self, file):
        try:
            with transaction.atomic():
                locked_file = File.objects.select_for_update(of=("self",)).get(pk=file.pk)
                storage = self._storage(locked_file.storage_alias)
                locked_file.product_files.all().delete()
                locked_file.status = self._status(self.STATUS_DELETED)
                locked_file.deleted_at = locked_file.deleted_at or timezone.now()
                locked_file.save(update_fields=["status", "deleted_at", "updated_at"])
        except Exception as exc:
            raise self.Error("The file could not be deleted.", file=file) from exc
        try:
            storage.delete(locked_file.object_key)
        except Exception as exc:
            locked_file.status = self._status(self.STATUS_FAILED)
            locked_file.save(update_fields=["status", "updated_at"])
            raise self.Error("The stored object could not be deleted.", file=locked_file) from exc
        file.status = locked_file.status
        file.deleted_at = locked_file.deleted_at
        file.updated_at = locked_file.updated_at
        return file

    def update_metadata(self, file, metadata):
        file.metadata = metadata
        file.save(update_fields=["metadata", "updated_at"])
        return file

    def list(self, *, search="", status=None, file_type=None, storage_alias=None, ordering="-created_at"):
        queryset = File.objects.select_related("status", "created_by")
        if search:
            queryset = queryset.filter(
                Q(original_name__icontains=search)
                | Q(object_key__icontains=search)
                | Q(checksum__icontains=search)
            )
        if status:
            queryset = queryset.filter(status__name=status)
        if file_type:
            queryset = queryset.filter(file_type=file_type)
        if storage_alias:
            queryset = queryset.filter(storage_alias=storage_alias)
        field = ordering.lstrip("-")
        if field not in self.ORDERING_FIELDS:
            raise self.Error("Invalid file ordering.")
        return queryset.order_by(ordering, "-created_at")

    def orphans(
        self,
        *,
        search="",
        file_type=None,
        storage_alias=None,
        ordering="-created_at",
    ):
        return self.list(
            search=search,
            status=self.STATUS_AVAILABLE,
            file_type=file_type,
            storage_alias=storage_alias,
            ordering=ordering,
        ).filter(product_files__isnull=True)

    @transaction.atomic
    def migrate_to_alias(self, file, target_alias):
        original_file = file
        file = File.objects.select_for_update(of=("self",)).select_related(
            "status"
        ).get(pk=file.pk)
        if file.status.name != self.STATUS_AVAILABLE:
            raise self.Error("Only available files can be migrated.", file=file)
        if target_alias == file.storage_alias:
            return file
        source = self._storage(file.storage_alias)
        target = self._storage(target_alias)
        target_key = None
        switched = False
        try:
            with source.open(file.object_key, "rb") as source_file:
                target_key = target.save(file.object_key, source_file)
            checksum = hashlib.sha256()
            size = 0
            with target.open(target_key, "rb") as copied_file:
                chunks = getattr(copied_file, "chunks", None)
                iterator = chunks() if chunks else iter(lambda: copied_file.read(64 * 1024), b"")
                for chunk in iterator:
                    checksum.update(chunk)
                    size += len(chunk)
            if size != file.size or checksum.hexdigest() != file.checksum:
                raise self.Error("The copied file failed verification.", file=file)
            old_alias, old_key = file.storage_alias, file.object_key
            file.storage_alias = target_alias
            file.object_key = target_key
            file.save(update_fields=["storage_alias", "object_key", "updated_at"])
            switched = True
            try:
                self._storage(old_alias).delete(old_key)
            except Exception:
                logger.exception(
                    "File %s migrated but source object %s:%s could not be removed.",
                    file.pk,
                    old_alias,
                    old_key,
                )
            original_file.storage_alias = file.storage_alias
            original_file.object_key = file.object_key
            original_file.updated_at = file.updated_at
            return original_file
        except self.Error:
            if target_key and not switched:
                target.delete(target_key)
            raise
        except Exception as exc:
            if target_key and not switched:
                try:
                    target.delete(target_key)
                except Exception:
                    pass
            raise self.Error("The file could not be migrated.", file=file) from exc

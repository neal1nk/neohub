from django.contrib import admin

from .models import (
    Assignment,
    AssignmentFile,
    Material,
    MaterialFile,
    Notification,
    Submission,
    SubmissionFile,
)


class MaterialFileInline(admin.TabularInline):
    model = MaterialFile
    extra = 0


class AssignmentFileInline(admin.TabularInline):
    model = AssignmentFile
    extra = 0


class SubmissionFileInline(admin.TabularInline):
    model = SubmissionFile
    extra = 0


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "student__username", "student__profile__display_name")
    inlines = [MaterialFileInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "assignment_type", "student", "deadline")
    list_filter = ("assignment_type", "deadline")
    search_fields = ("title", "student__username")
    inlines = [AssignmentFileInline]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "submitted_at", "grade")
    search_fields = ("assignment__title",)
    inlines = [SubmissionFileInline]


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")

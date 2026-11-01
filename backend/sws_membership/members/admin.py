"""Django admin for members: lookup and corrections by the society's admins."""

from django.contrib import admin

from sws_membership.members.models import Member, MemberRoleAssignment, MemberSport


class RoleInline(admin.TabularInline):
    model = MemberRoleAssignment
    extra = 0


class SportInline(admin.TabularInline):
    model = MemberSport
    extra = 0


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("member_number", "last_name", "first_name", "email", "date_of_birth")
    search_fields = ("member_number", "last_name", "first_name", "email")
    ordering = ("last_name", "first_name")
    inlines = [RoleInline, SportInline]
    exclude = ("password",)
    readonly_fields = ("created_at", "updated_at", "last_login")

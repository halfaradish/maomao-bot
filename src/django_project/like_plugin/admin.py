from django.contrib import admin
from .models import LikeRecord

@admin.register(LikeRecord)
class LikeRecordAdmin(admin.ModelAdmin):
    list_display = ('nickname', 'user_id', 'count', 'group_name')
    search_fields = ('nickname', 'user_id')
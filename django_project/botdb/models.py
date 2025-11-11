# -*- coding: utf-8 -*-
from django.db import models
from django.utils import timezone
import pytz

# 北京时区
BEIJING_TZ = pytz.timezone("Asia/Shanghai")


def beijing_now():
    """
    返回北京时区的当前时间（naive datetime，用于存储到数据库）
    当 USE_TZ = False 时，Django 直接存储 naive datetime，不会进行时区转换
    由于 TIME_ZONE = "Asia/Shanghai"，timezone.now() 返回的就是北京时区的 naive datetime
    """
    # 当 USE_TZ = False 时，timezone.now() 返回的是本地时区（Asia/Shanghai）的 naive datetime
    return timezone.now()


class MessageEventLog(models.Model):
    class SenderSex(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        UNKNOWN = "unknown"

    class SenderRole(models.TextChoices):
        OWNER = "owner"
        ADMIN = "admin"
        MEMBER = "member"

    id = models.BigAutoField(primary_key=True)
    message_id = models.IntegerField(unique=True)
    self_id = models.BigIntegerField()
    user_id = models.BigIntegerField()
    message_type = models.CharField(max_length=10)
    group_id = models.BigIntegerField(null=True, blank=True)
    sub_type = models.CharField(max_length=20)
    post_type = models.CharField(max_length=20, default="message")
    time = models.IntegerField()
    raw_message = models.TextField()
    message_json = models.JSONField()
    to_me = models.BooleanField(default=False)
    reply_json = models.JSONField(null=True, blank=True)
    sender_nickname = models.CharField(max_length=100)
    sender_card = models.CharField(max_length=100, null=True, blank=True)
    sender_sex = models.CharField(
        max_length=10, choices=SenderSex.choices, default=SenderSex.UNKNOWN
    )
    sender_age = models.SmallIntegerField(null=True, blank=True)
    sender_role = models.CharField(
        max_length=10, choices=SenderRole.choices, default=SenderRole.MEMBER
    )
    anonymous_flag = models.CharField(max_length=100, null=True, blank=True)
    anonymous_name = models.CharField(max_length=50, null=True, blank=True)
    anonymous_id = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)

    def save(self, *args, **kwargs):
        """重写 save 方法，确保 updated_at 每次保存时都更新为北京时间"""
        # 如果对象已存在（有 id），更新 updated_at
        if self.pk:
            self.updated_at = beijing_now()
        # 如果对象不存在（新建），created_at 和 updated_at 都使用 default
        elif not self.created_at:
            self.created_at = beijing_now()
            self.updated_at = beijing_now()
        super().save(*args, **kwargs)

    class Meta:
        db_table = "messages_event_logs"
        indexes = [
            models.Index(fields=["user_id"], name="idx_user_id"),
            models.Index(fields=["group_id"], name="idx_group_id"),
            models.Index(fields=["time"], name="idx_time"),
            models.Index(fields=["to_me"], name="idx_to_me"),
            models.Index(fields=["message_type", "group_id"], name="idx_type_group"),
            models.Index(fields=["created_at"], name="idx_created_at"),
        ]


class TodoReminder(models.Model):
    id = models.BigAutoField(primary_key=True)
    group_id = models.BigIntegerField()
    user_id = models.BigIntegerField()
    target_user_id = models.BigIntegerField(null=True, blank=True)
    content = models.TextField()
    remind_time = models.DateTimeField()
    remind_type = models.CharField(max_length=20, default="once")
    status = models.CharField(max_length=20, default="pending")
    created_by = models.BigIntegerField()
    last_modified_by = models.BigIntegerField()
    advance_remind_minutes = models.IntegerField(default=0)
    advance_reminded = models.BooleanField(default=False)

    execution_count = models.IntegerField(default=0)
    executed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)

    def save(self, *args, **kwargs):
        """重写 save 方法，确保 updated_at 每次保存时都更新为北京时间"""
        # 如果对象已存在（有 id），更新 updated_at
        if self.pk:
            self.updated_at = beijing_now()
        # 如果对象不存在（新建），created_at 和 updated_at 都使用 default
        elif not self.created_at:
            self.created_at = beijing_now()
            self.updated_at = beijing_now()
        super().save(*args, **kwargs)

    class Meta:
        db_table = "todo_reminders"
        indexes = [
            models.Index(fields=["group_id", "status", "remind_time"]),
            models.Index(fields=["user_id", "group_id", "status"]),
        ]


class TodoReminderLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    reminder = models.ForeignKey(TodoReminder, on_delete=models.CASCADE, related_name="logs")
    status = models.CharField(max_length=20)
    error_message = models.TextField(null=True, blank=True)
    execution_duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=beijing_now)

    class Meta:
        db_table = "todo_reminder_logs"
        indexes = [
            models.Index(fields=["reminder", "status"]),
        ]


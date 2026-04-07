# -*- coding: utf-8 -*-
from django.db import models
from django.utils import timezone
import pytz
import uuid

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
        max_length=10, choices=SenderSex.choices, default=SenderSex.UNKNOWN, null=True, blank=True
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


class QQRobotMessage(models.Model):
    class SceneType(models.TextChoices):
        GROUP = "group", "Group"
        GUILD = "guild", "Guild"
        PRIVATE = "private", "Private"

    class MessageStatus(models.TextChoices):
        SENT = "sent", "Sent"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot_uin = models.BigIntegerField()
    scene_type = models.CharField(max_length=10, choices=SceneType.choices)
    group_id = models.BigIntegerField(null=True, blank=True)
    guild_id = models.CharField(max_length=64, null=True, blank=True)
    channel_id = models.CharField(max_length=64, null=True, blank=True)
    msg_seq = models.BigIntegerField(null=True, blank=True)
    msg_id = models.CharField(max_length=128, null=True, blank=True)
    content = models.TextField()
    attachment = models.JSONField(default=dict, blank=True)
    target_members = models.JSONField(default=list, blank=True)
    sent_at = models.DateTimeField(default=beijing_now)
    remind_rule = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=MessageStatus.choices, default=MessageStatus.SENT
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)

    def save(self, *args, **kwargs):
        if self.pk:
            self.updated_at = beijing_now()
        elif not self.created_at:
            now = beijing_now()
            self.created_at = now
            self.updated_at = now
        super().save(*args, **kwargs)

    class Meta:
        db_table = "qq_robot_messages"
        indexes = [
            models.Index(fields=["bot_uin"], name="idx_qq_msg_bot_uin"),
            models.Index(fields=["scene_type"], name="idx_qq_msg_scene"),
            models.Index(fields=["group_id"], name="idx_qq_msg_group"),
            models.Index(fields=["guild_id"], name="idx_qq_msg_guild"),
            models.Index(fields=["msg_id"], name="idx_qq_msg_id"),
            models.Index(fields=["status"], name="idx_qq_msg_status"),
            models.Index(fields=["sent_at"], name="idx_qq_msg_sent_at"),
        ]


class QQMessageReaction(models.Model):
    id = models.BigAutoField(primary_key=True)
    message = models.ForeignKey(
        QQRobotMessage, on_delete=models.CASCADE, related_name="reactions"
    )
    reactor_uin = models.BigIntegerField()
    reaction_type = models.CharField(max_length=64)
    reacted_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)
    raw_event = models.JSONField(default=dict, blank=True)

    def save(self, *args, **kwargs):
        if self.pk:
            self.updated_at = beijing_now()
        elif not self.reacted_at:
            now = beijing_now()
            self.reacted_at = now
            self.updated_at = now
        super().save(*args, **kwargs)

    class Meta:
        db_table = "qq_message_reactions"
        indexes = [
            models.Index(fields=["reactor_uin"], name="idx_qq_react_reactor"),
            models.Index(fields=["reaction_type"], name="idx_qq_react_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "reactor_uin"], name="uq_qq_message_reactor"
            )
        ]


class QQMessageReceiptSummary(models.Model):
    message = models.OneToOneField(
        QQRobotMessage,
        on_delete=models.CASCADE,
        related_name="receipt_summary",
        primary_key=True,
    )
    expected_count = models.IntegerField(default=0)
    confirmed_count = models.IntegerField(default=0)
    outstanding_members = models.JSONField(default=list, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    reminder_stage = models.IntegerField(default=0)
    next_reminder_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)

    def save(self, *args, **kwargs):
        if self.pk:
            self.updated_at = beijing_now()
        elif not self.created_at:
            now = beijing_now()
            self.created_at = now
            self.updated_at = now
        super().save(*args, **kwargs)

    class Meta:
        db_table = "qq_message_receipt_summary"
        indexes = [
            models.Index(fields=["expected_count"], name="idx_qq_receipt_expected"),
            models.Index(fields=["confirmed_count"], name="idx_qq_receipt_confirmed"),
            models.Index(fields=["next_reminder_at"], name="idx_qq_receipt_next"),
        ]


class QQMessageReminder(models.Model):
    class ReminderType(models.TextChoices):
        GROUP = "group", "Group"
        PRIVATE = "private", "Private"
        EMAIL = "email", "Email"

    id = models.BigAutoField(primary_key=True)
    message = models.ForeignKey(
        QQRobotMessage, on_delete=models.CASCADE, related_name="reminders"
    )
    reminder_type = models.CharField(
        max_length=20, choices=ReminderType.choices, default=ReminderType.GROUP
    )
    payload = models.JSONField(default=dict, blank=True)
    triggered_at = models.DateTimeField(default=beijing_now)
    created_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)

    def save(self, *args, **kwargs):
        if self.pk:
            self.updated_at = beijing_now()
        elif not self.created_at:
            now = beijing_now()
            self.created_at = now
            self.updated_at = now
        super().save(*args, **kwargs)

    class Meta:
        db_table = "qq_message_reminders"
        indexes = [
            models.Index(fields=["reminder_type"], name="idx_qq_reminder_type"),
            models.Index(fields=["triggered_at"], name="idx_qq_reminder_triggered"),
        ]


class Group(models.Model):
    """
    用户分组信息

    用于 `group ls` 命令列出所有可用分组
    """

    name = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='分组标识',
        help_text='命令行中使用的分组名'
    )
    display_name = models.CharField(
        max_length=128,
        blank=True,
        verbose_name='展示名称',
        help_text='可选的友好显示名称'
    )
    description = models.TextField(
        blank=True,
        verbose_name='描述',
        help_text='分组用途说明'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )

    class Meta:
        db_table = 'group'
        verbose_name = '分组'
        verbose_name_plural = '分组列表'
        ordering = ['name']

    def __str__(self):
        return self.display_name or self.name


class GroupMember(models.Model):
    """
    分组成员关系

    支持 `group add QQ号 组名` 命令
    """

    group = models.ForeignKey(
        Group,
        to_field='name',
        related_name='members',
        on_delete=models.CASCADE,
        verbose_name='分组',
        db_column='group_name'  # 数据库列名使用 group_name，更直观
    )
    qq_id = models.BigIntegerField(
        verbose_name='QQ号',
        help_text='成员 QQ 号'
    )
    qq_nickname = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='QQ 昵称',
        help_text='成员昵称或群名片'
    )
    added_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='加入时间'
    )

    class Meta:
        db_table = 'group_member'
        verbose_name = '分组成员'
        verbose_name_plural = '分组成员列表'
        unique_together = ('group', 'qq_id')
        indexes = [
            models.Index(fields=['qq_id']),
        ]

    def __str__(self):
        return f"{self.qq_id} @ {self.group.name}"
class MonitoredGroup(models.Model):
    """QQ群监控列表"""
    id = models.BigAutoField(primary_key=True)
    group_id = models.BigIntegerField(unique=True, verbose_name='QQ群号')
    group_name = models.CharField(max_length=100, default='', verbose_name='群名称')
    is_active = models.BooleanField(default=True, verbose_name='是否监控')
    created_at = models.DateTimeField(default=beijing_now)
    updated_at = models.DateTimeField(default=beijing_now)

    def save(self, *args, **kwargs):
        if self.pk:
            self.updated_at = beijing_now()
        elif not self.created_at:
            self.created_at = beijing_now()
            self.updated_at = beijing_now()
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'monitored_groups'
        verbose_name = '监控群'
        verbose_name_plural = '监控群列表'
        indexes = [
            models.Index(fields=['group_id'], name='idx_monitored_group_id'),
            models.Index(fields=['is_active'], name='idx_monitored_is_active'),
        ]
class GroupFile(models.Model):
    """群文件记录"""
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(
        MonitoredGroup, 
        on_delete=models.CASCADE, 
        related_name='files',
        verbose_name='所属群'
    )
    file_id = models.CharField(max_length=100, verbose_name='QQ文件ID')
    file_name = models.CharField(max_length=255, verbose_name='文件名')
    file_size = models.BigIntegerField(default=0, verbose_name='文件大小')
    file_path = models.CharField(max_length=500, verbose_name='本地存储路径')
    file_hash = models.CharField(max_length=32, db_index=True, verbose_name='MD5哈希')
    uploader_id = models.BigIntegerField(default=0, verbose_name='上传者QQ')
    downloaded_at = models.DateTimeField(default=beijing_now, verbose_name='下载时间')

    class Meta:
        db_table = 'group_files'
        verbose_name = '群文件'
        verbose_name_plural = '群文件列表'
        indexes = [
            models.Index(fields=['file_hash'], name='idx_file_hash'),
            models.Index(fields=['group', 'downloaded_at'], name='idx_group_downloaded'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['file_id', 'group'], name='uq_file_per_group'),
        ]
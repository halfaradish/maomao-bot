# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import (
    MessageEventLog,
    TodoReminder,
    TodoReminderLog,
    QQRobotMessage,
    QQMessageReaction,
    QQMessageReceiptSummary,
    QQMessageReminder,
    Group,
    GroupMember,
)


@admin.register(MessageEventLog)
class MessageEventLogAdmin(admin.ModelAdmin):
    """消息事件日志管理"""
    list_display = ['id', 'message_id', 'user_id', 'group_id', 'message_type', 'sender_nickname', 'created_at']
    list_filter = ['message_type', 'post_type', 'to_me', 'created_at']
    search_fields = ['user_id', 'group_id', 'sender_nickname', 'raw_message']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(TodoReminder)
class TodoReminderAdmin(admin.ModelAdmin):
    """待办提醒管理"""
    list_display = ['id', 'group_id', 'user_id', 'target_user_id', 'content', 'remind_time', 'status', 'created_at']
    list_filter = ['status', 'remind_type', 'remind_time', 'created_at']
    search_fields = ['content', 'user_id', 'target_user_id', 'group_id']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'remind_time'
    ordering = ['-remind_time']


@admin.register(TodoReminderLog)
class TodoReminderLogAdmin(admin.ModelAdmin):
    """待办提醒日志管理"""
    list_display = ['id', 'reminder', 'status', 'execution_duration_ms', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['reminder__content']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(QQRobotMessage)
class QQRobotMessageAdmin(admin.ModelAdmin):
    """QQ机器人消息管理"""
    list_display = ['id', 'bot_uin', 'scene_type', 'group_id', 'status', 'sent_at', 'created_at']
    list_filter = ['scene_type', 'status', 'sent_at', 'created_at']
    search_fields = ['bot_uin', 'group_id', 'content', 'msg_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'sent_at'
    ordering = ['-sent_at']
    filter_horizontal = []


@admin.register(QQMessageReaction)
class QQMessageReactionAdmin(admin.ModelAdmin):
    """QQ消息表情反应管理"""
    list_display = ['id', 'message', 'reactor_uin', 'reaction_type', 'reacted_at']
    list_filter = ['reaction_type', 'reacted_at']
    search_fields = ['reactor_uin', 'message__content']
    readonly_fields = ['reacted_at', 'updated_at']
    date_hierarchy = 'reacted_at'
    ordering = ['-reacted_at']


@admin.register(QQMessageReceiptSummary)
class QQMessageReceiptSummaryAdmin(admin.ModelAdmin):
    """QQ消息回执汇总管理"""
    list_display = ['message', 'expected_count', 'confirmed_count', 'reminder_stage', 'last_checked_at']
    list_filter = ['reminder_stage', 'last_checked_at']
    search_fields = ['message__content']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'last_checked_at'
    ordering = ['-last_checked_at']


@admin.register(QQMessageReminder)
class QQMessageReminderAdmin(admin.ModelAdmin):
    """QQ消息提醒管理"""
    list_display = ['id', 'message', 'reminder_type', 'triggered_at', 'created_at']
    list_filter = ['reminder_type', 'triggered_at', 'created_at']
    search_fields = ['message__content']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'triggered_at'
    ordering = ['-triggered_at']


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """分组管理"""
    list_display = ['name', 'display_name', 'description', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at']
    search_fields = ['name', 'display_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['name']


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    """分组成员管理"""
    list_display = ['id', 'group', 'qq_id', 'qq_nickname', 'added_at']
    list_filter = ['group', 'added_at']
    search_fields = ['qq_id', 'qq_nickname', 'group__name']
    readonly_fields = ['added_at']
    date_hierarchy = 'added_at'
    ordering = ['-added_at']


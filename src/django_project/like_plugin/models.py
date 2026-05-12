from django.db import models

class LikeRecord(models.Model):
    user_id = models.CharField(max_length=100, unique=True, verbose_name="用户ID")
    nickname = models.CharField(max_length=255, blank=True, null=True)
    count = models.IntegerField(default=0, verbose_name="点赞数")
    is_following = models.BooleanField(default=False, verbose_name="是否订阅")
    
    # 新增字段
    group_number = models.CharField(max_length=100, blank=True, null=True)
    group_name = models.CharField(max_length=255, blank=True, null=True)
    subscription_source = models.CharField(max_length=255, default="diting_bot")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nickname}({self.user_id})"

class PluginConfig(models.Model):
    """
    插件配置表（替代原来的 JSON 配置）
    用于存储 ban_group_users 等全局配置
    """
    key = models.CharField(max_length=100, unique=True, verbose_name="配置键")
    value = models.TextField(verbose_name="配置值")  # 存 JSON 字符串

    class Meta:
        verbose_name = "插件配置"
        verbose_name_plural = verbose_name

    @staticmethod
    def get_ban_groups():
        """获取禁止点赞的群列表"""
        obj, _ = PluginConfig.objects.update_or_create(
            key="ban_group_users",
            defaults={"value": "[]"}
        )
        import json
        return json.loads(obj.value)

    @staticmethod
    def set_ban_groups(group_list):
        """设置禁止点赞的群列表"""
        import json
        PluginConfig.objects.update_or_create(
            key="ban_group_users",
            defaults={"value": json.dumps(group_list)}
        )
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
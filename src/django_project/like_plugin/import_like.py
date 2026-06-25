import os
import json
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from like_plugin.models import LikeRecord, PluginConfig

def main():
    # 注意：这里指向的是容器内的路径
    json_path = "/app/src/django_project/like.json"
    
    if not os.path.exists(json_path):
        print(f"❌ 错误：找不到文件 {json_path}")
        print("请确保你已经把 like.json 复制到了容器里")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📂 正在读取 {len(data.get('liked_by_bot', {}))} 条用户数据...")
    
    # 导入点赞记录
    liked_data = data.get("liked_by_bot", {})
    count = 0
    for uid, info in liked_data.items():
        LikeRecord.objects.update_or_create(
            user_id=uid,
            defaults={
                "nickname": info.get("nickname"),
                "count": info.get("count", 0),
                "is_following": info.get("follow", False),
            }
        )
        count += 1
        if count % 50 == 0:
            print(f"  已导入 {count} 条...")

    # 导入禁止群列表
    ban_groups = data.get("ban_group_users", [])
    PluginConfig.set_ban_groups(ban_groups)
    
    print(f"✅ 成功导入 {count} 条点赞记录！")

if __name__ == "__main__":
    main()
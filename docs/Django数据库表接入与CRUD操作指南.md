# Django 数据库表接入与 CRUD 操作指南

## 1. 项目概述

本文档旨在指导开发者如何在当前 NoneBot 项目中接入新的数据库表，并实现完整的 CRUD（创建、读取、更新、删除）操作，以支持 `src/plugins` 目录下的插件功能需求。

### 1.1 项目结构

```
d:\Project\technical_group\diting\nonebot\
├── src/
│   ├── common/
│   │   └── django_crud.py       # 异步 CRUD 操作工具类
│   ├── django_project/          # Django 项目目录
│   │   ├── botdb/               # 应用目录
│   │   │   └── models.py        # 数据库模型定义
│   │   └── django_project/
│   │       └── settings.py      # Django 配置文件
│   └── plugins/                 # 插件目录
│       └── logging_info/
│           └── message_dao.py   # 示例 DAO 实现
└── docs/                        # 文档目录
```

### 1.2 技术栈

- **框架**: NoneBot 2
- **数据库**: MySQL
- **ORM**: Django ORM
- **异步支持**: asgiref.sync_to_async

## 2. 数据库表接入流程

### 2.1 模型定义规范

1. **在 `botdb/models.py` 中添加模型类**

   模型类应继承自 `django.db.models.Model`，并遵循以下规范：

   - 使用 `BigAutoField` 作为主键
   - 为时间字段添加 `created_at` 和 `updated_at`
   - 重写 `save()` 方法以更新 `updated_at`
   - 在 `Meta` 类中定义表名和索引

   **示例模型定义**：

   ```python
   from django.db import models
   from django.utils import timezone
   import pytz

   # 北京时区
   BEIJING_TZ = pytz.timezone("Asia/Shanghai")

   def beijing_now():
       """
       返回北京时区的当前时间（naive datetime）
       """
       return timezone.now()

   class ExampleModel(models.Model):
       """示例模型"""
       id = models.BigAutoField(primary_key=True)
       name = models.CharField(max_length=100, verbose_name="名称")
       value = models.IntegerField(default=0, verbose_name="值")
       is_active = models.BooleanField(default=True, verbose_name="是否激活")
       created_at = models.DateTimeField(default=beijing_now, verbose_name="创建时间")
       updated_at = models.DateTimeField(default=beijing_now, verbose_name="更新时间")

       def save(self, *args, **kwargs):
           """重写 save 方法，确保 updated_at 每次保存时都更新"""
           if self.pk:
               self.updated_at = beijing_now()
           elif not self.created_at:
               self.created_at = beijing_now()
               self.updated_at = beijing_now()
           super().save(*args, **kwargs)

       class Meta:
           db_table = "example_models"  # 数据库表名
           verbose_name = "示例模型"
           verbose_name_plural = "示例模型列表"
           indexes = [
               models.Index(fields=["name"], name="idx_example_name"),
               models.Index(fields=["is_active"], name="idx_example_active"),
           ]
   ```

### 2.2 数据库迁移操作步骤

1. **进入 Django 项目目录**

   ```bash
   cd d:\Project\technical_group\diting\nonebot\src\django_project
   ```

2. **生成迁移文件**

   ```bash
   python manage.py makemigrations botdb
   ```

   这将为新添加的模型生成迁移文件。

3. **执行迁移**

   ```bash
   python manage.py migrate
   ```

   这将在数据库中创建或更新表结构。

### 2.3 验证方法

1. **检查迁移状态**

   ```bash
   python manage.py showmigrations
   ```

2. **查看数据库表结构**

   使用数据库管理工具（如 Navicat、phpMyAdmin）检查表是否已创建，字段是否正确。

3. **测试数据操作**

   编写简单的测试脚本，验证数据的增删改查操作是否正常。

## 3. CRUD 功能实现指南

### 3.1 基于 `django_crud.py` 的实现

`django_crud.py` 提供了以下异步 CRUD 函数：

- `async_create_record()`: 创建记录
- `async_get_one()`: 获取单条记录
- `async_get_many()`: 获取多条记录
- `async_update_records()`: 更新记录
- `async_delete_records()`: 删除记录

### 3.2 标准 CRUD 接口实现

#### 3.2.1 创建数据访问对象 (DAO)

在插件目录中创建 DAO 类，例如 `example_dao.py`：

```python
from nonebot import logger
from typing import List, Dict, Optional
from datetime import datetime
import pytz
from django.db import IntegrityError
from ...common.django_crud import (
    async_create_record, async_get_one, async_get_many,
    async_update_records, async_delete_records, init_django_if_needed
)

init_django_if_needed()
from botdb.models import ExampleModel

# 北京时区
BEIJING_TZ = pytz.timezone("Asia/Shanghai")


class ExampleDAO:
    """
    示例数据访问对象（DAO）
    """

    @staticmethod
    async def create_example(name: str, value: int = 0) -> bool:
        """
        创建示例记录
        :param name: 名称
        :param value: 值
        :return: 是否成功
        """
        try:
            await async_create_record(
                ExampleModel,
                name=name,
                value=value
            )
            return True
        except IntegrityError as e:
            logger.error(f"创建示例记录失败 (name={name}): {e}")
            return False
        except Exception as e:
            logger.error(f"创建示例记录失败: {e}")
            return False

    @staticmethod
    async def get_example_by_id(example_id: int) -> Optional[ExampleModel]:
        """
        根据 ID 获取示例记录
        :param example_id: 示例 ID
        :return: 示例记录或 None
        """
        return await async_get_one(ExampleModel, id=example_id)

    @staticmethod
    async def get_examples(limit: int = 100, is_active: bool = None) -> List[Dict]:
        """
        获取示例记录列表
        :param limit: 限制数量
        :param is_active: 是否激活（可选）
        :return: 示例记录列表
        """
        filters = {}
        if is_active is not None:
            filters["is_active"] = is_active

        rows = await async_get_many(
            ExampleModel,
            filters=filters,
            order_by=["-created_at"],
            limit=limit
        )

        result = []
        for r in rows:
            result.append({
                "id": r.id,
                "name": r.name,
                "value": r.value,
                "is_active": r.is_active,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        return result

    @staticmethod
    async def update_example(example_id: int, updates: Dict) -> bool:
        """
        更新示例记录
        :param example_id: 示例 ID
        :param updates: 更新的字段
        :return: 是否成功
        """
        try:
            updated_count = await async_update_records(
                ExampleModel,
                filters={"id": example_id},
                updates=updates
            )
            return updated_count > 0
        except Exception as e:
            logger.error(f"更新示例记录失败 (id={example_id}): {e}")
            return False

    @staticmethod
    async def delete_example(example_id: int) -> bool:
        """
        删除示例记录
        :param example_id: 示例 ID
        :return: 是否成功
        """
        try:
            deleted_count = await async_delete_records(
                ExampleModel,
                id=example_id
            )
            return deleted_count > 0
        except Exception as e:
            logger.error(f"删除示例记录失败 (id={example_id}): {e}")
            return False


example_dao = ExampleDAO()
```

### 3.3 高级查询示例

#### 3.3.1 复杂条件查询

```python
from django.db.models import Q
from asgiref.sync import sync_to_async

async def search_examples(keyword: str, min_value: int = 0, limit: int = 50) -> List[Dict]:
    """
    搜索示例记录
    :param keyword: 关键词
    :param min_value: 最小值
    :param limit: 限制数量
    :return: 示例记录列表
    """
    try:
        def _search_sync():
            return list(
                ExampleModel.objects.filter(
                    Q(name__icontains=keyword) & Q(value__gte=min_value)
                ).order_by("-created_at")[:limit]
            )
        
        rows = await sync_to_async(_search_sync)()
        # 处理结果...
        return result
    except Exception as e:
        logger.error(f"搜索示例记录失败: {e}")
        return []
```

## 4. 与插件集成方法

### 4.1 接口调用规范

1. **在插件中导入 DAO**

   ```python
   from .example_dao import example_dao
   ```

2. **异步调用**

   由于 NoneBot 是异步框架，所有数据库操作都应该在异步函数中进行：

   ```python
   from nonebot import on_command
   from nonebot.adapters.onebot.v11 import MessageEvent

   example_cmd = on_command("example")

   @example_cmd.handle()
async def handle_example(event: MessageEvent):
    # 创建示例
    success = await example_dao.create_example("测试", 100)
    if success:
        await example_cmd.finish("创建成功")
    else:
        await example_cmd.finish("创建失败")
   ```

### 4.2 数据格式要求

1. **输入数据验证**

   在调用 DAO 方法前，应验证输入数据的有效性：

   ```python
   async def create_example_handler(event: MessageEvent):
    args = event.get_plaintext().split()
    if len(args) < 1:
        await example_cmd.finish("请提供名称")
    
    name = args[0]
    value = int(args[1]) if len(args) > 1 else 0
    
    # 验证数据
    if not name or len(name) > 100:
        await example_cmd.finish("名称长度应在 1-100 之间")
    
    success = await example_dao.create_example(name, value)
    # 处理结果...
   ```

2. **输出数据格式化**

   DAO 方法应返回结构化的数据，便于插件处理：

   ```python
   async def get_examples_handler(event: MessageEvent):
    examples = await example_dao.get_examples(limit=10)
    
    if not examples:
        await example_cmd.finish("暂无示例数据")
    
    # 格式化输出
    message = "示例列表：\n"
    for example in examples:
        message += f"ID: {example['id']}, 名称: {example['name']}, 值: {example['value']}\n"
    
    await example_cmd.finish(message)
   ```

### 4.3 错误处理机制

1. **异常捕获**

   DAO 方法应捕获并处理数据库异常，返回布尔值或空列表/None 表示操作结果：

   ```python
   async def safe_operation():
    try:
        result = await example_dao.some_operation()
        if not result:
            # 处理失败情况
            pass
    except Exception as e:
        logger.error(f"操作失败: {e}")
        # 向用户反馈错误
   ```

2. **错误日志**

   使用 NoneBot 的 logger 记录错误信息：

   ```python
   from nonebot import logger

   try:
    # 数据库操作
   except Exception as e:
    logger.error(f"数据库操作失败: {e}")
    # 处理错误
   ```

## 5. 项目结构说明

### 5.1 新功能模块组织方式

1. **模型定义**

   在 `src/django_project/botdb/models.py` 中添加新模型类。

2. **数据访问对象**

   在插件目录中创建 `*_dao.py` 文件，实现与数据库的交互逻辑。

3. **插件实现**

   在插件目录中创建 `plugin.py` 或 `__init__.py` 文件，实现业务逻辑。

### 5.2 目录结构示例

```
src/
├── common/
│   └── django_crud.py          # 核心 CRUD 工具
├── django_project/
│   ├── botdb/
│   │   ├── __init__.py
│   │   └── models.py           # 模型定义
│   └── django_project/
│       └── settings.py         # Django 配置
└── plugins/
    └── example_plugin/         # 插件目录
        ├── __init__.py         # 插件入口
        ├── config.py           # 插件配置
        └── example_dao.py      # 数据访问对象
```

## 6. 完整示例

### 6.1 完整的插件实现

**`src/plugins/example_plugin/__init__.py`**：

```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from .example_dao import example_dao

# 注册命令
example_cmd = on_command("example")
create_cmd = on_command("create_example")
list_cmd = on_command("list_examples")
update_cmd = on_command("update_example")
delete_cmd = on_command("delete_example")

@example_cmd.handle()
async def handle_example(event: MessageEvent):
    await example_cmd.finish("示例插件命令")

@create_cmd.handle()
async def handle_create(event: MessageEvent):
    args = event.get_plaintext().split()
    if len(args) < 1:
        await create_cmd.finish("请提供示例名称")
    
    name = args[0]
    value = int(args[1]) if len(args) > 1 else 0
    
    success = await example_dao.create_example(name, value)
    if success:
        await create_cmd.finish(f"创建示例 '{name}' 成功")
    else:
        await create_cmd.finish("创建示例失败")

@list_cmd.handle()
async def handle_list(event: MessageEvent):
    examples = await example_dao.get_examples(limit=10)
    
    if not examples:
        await list_cmd.finish("暂无示例数据")
    
    message = "示例列表：\n"
    for example in examples:
        message += f"ID: {example['id']}, 名称: {example['name']}, 值: {example['value']}\n"
    
    await list_cmd.finish(message)

@update_cmd.handle()
async def handle_update(event: MessageEvent):
    args = event.get_plaintext().split()
    if len(args) < 2:
        await update_cmd.finish("请提供示例 ID 和新值")
    
    try:
        example_id = int(args[0])
        new_value = int(args[1])
    except ValueError:
        await update_cmd.finish("ID 和值必须为数字")
    
    success = await example_dao.update_example(example_id, {"value": new_value})
    if success:
        await update_cmd.finish(f"更新示例 ID {example_id} 成功")
    else:
        await update_cmd.finish("更新示例失败")

@delete_cmd.handle()
async def handle_delete(event: MessageEvent):
    args = event.get_plaintext().split()
    if len(args) < 1:
        await delete_cmd.finish("请提供示例 ID")
    
    try:
        example_id = int(args[0])
    except ValueError:
        await delete_cmd.finish("ID 必须为数字")
    
    success = await example_dao.delete_example(example_id)
    if success:
        await delete_cmd.finish(f"删除示例 ID {example_id} 成功")
    else:
        await delete_cmd.finish("删除示例失败")
```

### 6.2 完整的 DAO 实现

**`src/plugins/example_plugin/example_dao.py`**：

```python
from nonebot import logger
from typing import List, Dict, Optional
from datetime import datetime
import pytz
from django.db import IntegrityError
from ...common.django_crud import (
    async_create_record, async_get_one, async_get_many,
    async_update_records, async_delete_records, init_django_if_needed
)

init_django_if_needed()
from botdb.models import ExampleModel

# 北京时区
BEIJING_TZ = pytz.timezone("Asia/Shanghai")


class ExampleDAO:
    """
    示例数据访问对象（DAO）
    """

    @staticmethod
    async def create_example(name: str, value: int = 0) -> bool:
        """
        创建示例记录
        :param name: 名称
        :param value: 值
        :return: 是否成功
        """
        try:
            await async_create_record(
                ExampleModel,
                name=name,
                value=value
            )
            return True
        except IntegrityError as e:
            logger.error(f"创建示例记录失败 (name={name}): {e}")
            return False
        except Exception as e:
            logger.error(f"创建示例记录失败: {e}")
            return False

    @staticmethod
    async def get_example_by_id(example_id: int) -> Optional[ExampleModel]:
        """
        根据 ID 获取示例记录
        :param example_id: 示例 ID
        :return: 示例记录或 None
        """
        return await async_get_one(ExampleModel, id=example_id)

    @staticmethod
    async def get_examples(limit: int = 100, is_active: bool = None) -> List[Dict]:
        """
        获取示例记录列表
        :param limit: 限制数量
        :param is_active: 是否激活（可选）
        :return: 示例记录列表
        """
        filters = {}
        if is_active is not None:
            filters["is_active"] = is_active

        rows = await async_get_many(
            ExampleModel,
            filters=filters,
            order_by=["-created_at"],
            limit=limit
        )

        result = []
        for r in rows:
            result.append({
                "id": r.id,
                "name": r.name,
                "value": r.value,
                "is_active": r.is_active,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })
        return result

    @staticmethod
    async def update_example(example_id: int, updates: Dict) -> bool:
        """
        更新示例记录
        :param example_id: 示例 ID
        :param updates: 更新的字段
        :return: 是否成功
        """
        try:
            updated_count = await async_update_records(
                ExampleModel,
                filters={"id": example_id},
                updates=updates
            )
            return updated_count > 0
        except Exception as e:
            logger.error(f"更新示例记录失败 (id={example_id}): {e}")
            return False

    @staticmethod
    async def delete_example(example_id: int) -> bool:
        """
        删除示例记录
        :param example_id: 示例 ID
        :return: 是否成功
        """
        try:
            deleted_count = await async_delete_records(
                ExampleModel,
                id=example_id
            )
            return deleted_count > 0
        except Exception as e:
            logger.error(f"删除示例记录失败 (id={example_id}): {e}")
            return False


example_dao = ExampleDAO()
```

## 7. 最佳实践

1. **使用异步操作**：所有数据库操作都应使用 `django_crud.py` 中的异步函数
2. **错误处理**：捕获并记录数据库操作异常，向用户提供友好的错误信息
3. **数据验证**：在调用 DAO 方法前验证输入数据的有效性
4. **索引优化**：为常用查询字段创建索引，提高查询性能
5. **事务处理**：对于复杂操作，使用 Django 的事务管理确保数据一致性
6. **代码组织**：遵循项目现有的代码风格和目录结构
7. **文档注释**：为模型、DAO 方法和插件函数添加详细的文档注释

## 8. 常见问题与解决方案

### 8.1 Django 初始化失败

**问题**：`init_django_if_needed()` 失败

**解决方案**：
- 检查 `DJANGO_SETTINGS_MODULE` 环境变量
- 确保数据库连接参数正确
- 检查 PyMySQL 是否已安装（Windows 环境）

### 8.2 数据库迁移失败

**问题**：`python manage.py migrate` 失败

**解决方案**：
- 检查数据库连接
- 确保模型定义正确
- 尝试删除旧的迁移文件并重新生成

### 8.3 异步操作阻塞

**问题**：数据库操作导致机器人响应缓慢

**解决方案**：
- 确保所有数据库操作都在异步函数中进行
- 避免在同步函数中调用异步数据库操作
- 对于批量操作，考虑使用分页或异步批量处理

### 8.4 时区问题

**问题**：时间显示不正确

**解决方案**：
- 使用 `beijing_now()` 函数获取北京时间
- 在 DAO 中正确处理时区转换
- 确保 `settings.py` 中 `USE_TZ = False` 和 `TIME_ZONE = "Asia/Shanghai"`

## 9. 总结

本文档详细说明了如何在当前 NoneBot 项目中接入新的数据库表，并实现完整的 CRUD 操作。通过遵循本文档的指南，开发者可以：

1. 快速定义新的数据库模型并进行迁移
2. 基于 `django_crud.py` 实现标准的 CRUD 接口
3. 将数据库操作与插件无缝集成
4. 遵循项目现有的开发规范和最佳实践

希望本文档能够帮助开发者更加高效地开发和维护项目中的数据库相关功能。
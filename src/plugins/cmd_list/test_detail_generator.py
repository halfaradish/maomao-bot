import sys
import os
import asyncio

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from img_generator import _detail_html_builder, _generate_detail_img
from model import PluginUsageInfo

# 测试单个插件详情HTML生成功能
def test_detail_html_builder():
    # 创建测试数据
    test_plugin = PluginUsageInfo(
        name="测试插件",
        description="这是一个测试插件，用于测试详细信息展示功能",
        usage="使用方法：/test [参数]\n示例：/test hello",
        group="测试",
        module_name="test_plugin"
    )
    
    # 测试HTML生成
    html_content = _detail_html_builder(
        plugin_data=test_plugin,
        title="插件详情",
        desc="测试插件的详细信息"
    )
    
    # 验证结果
    assert html_content is not None, "HTML生成失败"
    assert "测试插件" in html_content, "插件名称未正确渲染"
    assert "这是一个测试插件" in html_content, "插件描述未正确渲染"
    assert "/test [参数]" in html_content, "插件使用方法未正确渲染"
    assert "测试" in html_content, "插件分组未正确渲染"
    assert "test_plugin" in html_content, "模块名未正确渲染"
    
    print("详情HTML生成测试通过！")

# 测试单个插件详情图片生成功能
async def test_detail_img_generator():
    # 创建测试数据
    test_plugin = PluginUsageInfo(
        name="测试插件",
        description="这是一个测试插件，用于测试详细信息展示功能",
        usage="使用方法：/test [参数]\n示例：/test hello",
        group="测试",
        module_name="test_plugin"
    )
    
    # 测试图片生成
    img = await _generate_detail_img(test_plugin)
    
    # 验证结果
    assert img is not None, "图片生成失败"
    assert isinstance(img, bytes), "图片应为二进制数据"
    assert len(img) > 0, "图片数据为空"
    
    # 保存测试图片
    with open("test_detail_output.png", "wb") as f:
        f.write(img)
    
    print("详情图片生成测试通过！测试图片已保存为 test_detail_output.png")

if __name__ == "__main__":
    test_detail_html_builder()
    asyncio.run(test_detail_img_generator())

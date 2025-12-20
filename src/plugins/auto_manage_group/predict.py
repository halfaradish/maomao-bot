import os
import torch
from transformers import BertTokenizerFast, BertForSequenceClassification

# ================== 配置区 ==================

# 确保这里的文件夹名字和你训练保存的名字一致
MODEL_DIR = os.path.join(os.path.dirname(__file__), "sell_ad_group_model")

# 判定阈值：只有模型确信度超过这个数才拦截
# 建议：纯模型模式下，建议设高一点（比如 0.8），防止日常聊天被误杀
THRESHOLD = 0.75

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
LABELS = ["ad", "group"]

# ================== 全局加载模型 ==================
# 放在函数外，确保插件启动时只加载一次，防止卡顿

print(f"🔄 正在加载 AI 模型 (设备: {DEVICE})...")
try:
    _tokenizer = BertTokenizerFast.from_pretrained(MODEL_DIR)
    _model = BertForSequenceClassification.from_pretrained(MODEL_DIR)
    _model.to(DEVICE)
    _model.eval()
    print("✅ AI 模型加载完成！")
except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    # 这里不抛出错误，防止 nonebot 启动崩溃，但预测时会报错
    _tokenizer = None
    _model = None


# ================== 核心预测函数 ==================

def predict(text: str) -> dict:
    """
    纯模型预测函数
    """
    # 0. 基础检查
    if not text or not _tokenizer or not _model:
        return {
            "label": "normal",
            "scores": {},
            "is_malicious": False
        }

    text = text.strip()

    # 1. 模型推理
    try:
        inputs = _tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128  # 建议稍微改大一点到 128，防止长广告被截断
        ).to(DEVICE)

        with torch.no_grad():
            logits = _model(**inputs).logits.squeeze(0)
            probs = torch.sigmoid(logits)

        # 2. 格式化分数
        scores = {
            LABELS[i]: float(probs[i])
            for i in range(len(LABELS))
        }

        # 3. 判定逻辑
        # 找出分数最高的那个标签
        hit = {k: v for k, v in scores.items() if v >= THRESHOLD}

        # 如果没有任何标签超过阈值 -> 正常消息
        if not hit:
            return {
                "label": "normal",
                "scores": scores,
                "is_malicious": False
            }

        # 取出分数最高的标签（是 ad 还是 group）
        label = max(hit, key=hit.get)

        return {
            "label": label,
            "scores": scores,
            "is_malicious": True
        }

    except Exception as e:
        print(f"❌ 预测出错: {e}")
        return {
            "label": "error",
            "scores": {},
            "is_malicious": False
        }

# ================== 本地测试入口 ==================

if __name__ == "__main__":
    print(f"🚀 纯模型检测已启动 (阈值: {THRESHOLD})")
    while True:
        try:
            t = input(">>> 请输入测试文本: ")
            res = predict(t)
            status = "🛑 拦截" if res["is_malicious"] else "✅ 放行"
            print(f"{status} | 标签: {res['label']} | 分数: {res['scores']}")
        except KeyboardInterrupt:
            break
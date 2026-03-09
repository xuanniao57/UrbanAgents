"""
Simple Kimi Test
简单测试Kimi API
"""

import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 直接设置环境变量进行测试
os.environ['KIMI_API_KEY'] = 'sk-866NFHzkzev3KJuhpc5UGi3jCKMn8UxESi9kwbzABQ6EjydP'
os.environ['KIMI_BASE_URL'] = 'https://api.moonshot.cn/v1'

# Kimi coding 使用相同的base URL
os.environ['KIMI_CODE_API_KEY'] = 'sk-kimi-QdnvIRVqZhZs2QbseBOOl4bREN7Wvn70wOk2Ob0SHjYbJoJLdgF513CoceFQnO4l'
os.environ['KIMI_CODE_API_BASE'] = 'https://api.moonshot.cn/v1'  # 使用相同的base URL

logger.info(f"KIMI_API_KEY: {os.getenv('KIMI_API_KEY', 'NOT SET')[:30]}...")
logger.info(f"KIMI_CODE_API_KEY: {os.getenv('KIMI_CODE_API_KEY', 'NOT SET')[:30]}...")

from openai import AsyncOpenAI

async def test_kimi_standard():
    """测试Kimi Standard"""
    logger.info("\n测试Kimi Standard (kimi-k2.5)...")
    
    client = AsyncOpenAI(
        api_key=os.getenv('KIMI_API_KEY'),
        base_url=os.getenv('KIMI_BASE_URL')
    )
    
    try:
        # Kimi k2.5 只支持 temperature=1
        response = await client.chat.completions.create(
            model="kimi-k2.5",
            messages=[
                {"role": "user", "content": "What is the capital of France? Answer in one word."}
            ],
            temperature=1,  # 必须设置为1
            max_tokens=100
        )
        
        result = response.choices[0].message.content
        logger.info(f"✅ 成功: {result}")
        return True
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False

async def test_kimi_coding():
    """测试Kimi Coding"""
    logger.info("\n测试Kimi Coding (kimi-for-coding)...")
    
    # 使用coding专用的API key
    client = AsyncOpenAI(
        api_key=os.getenv('KIMI_CODE_API_KEY'),
        base_url=os.getenv('KIMI_CODE_API_BASE')
    )
    
    try:
        response = await client.chat.completions.create(
            model="kimi-for-coding",  # 或 kimi-k2.5
            messages=[
                {"role": "system", "content": "You are an expert programmer."},
                {"role": "user", "content": "Write a Python function to add two numbers."}
            ],
            temperature=1,
            max_tokens=500
        )
        
        result = response.choices[0].message.content
        logger.info(f"✅ 成功: {result[:200]}...")
        return True
    except Exception as e:
        logger.error(f"❌ 失败: {e}")
        return False

async def test_kimi_vision():
    """测试Kimi视觉能力"""
    logger.info("\n测试Kimi视觉能力...")
    
    client = AsyncOpenAI(
        api_key=os.getenv('KIMI_API_KEY'),
        base_url=os.getenv('KIMI_BASE_URL')
    )
    
    # 尝试加载一张测试图像
    test_image_path = "d:\\GitHub_1\\world_agent\\urban-mobility-agent\\paper4_urban_svgagent\\third_party\\CityBench-main\\citydata\\remote_sensing\\Paris\\11266_16588.png"
    
    try:
        import base64
        from pathlib import Path
        
        if Path(test_image_path).exists():
            with open(test_image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode()
            
            response = await client.chat.completions.create(
                model="kimi-k2.5",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this remote sensing image in one sentence."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=1,
                max_tokens=200
            )
            
            result = response.choices[0].message.content
            logger.info(f"✅ 视觉分析成功: {result}")
            return True
        else:
            logger.warning(f"测试图像不存在: {test_image_path}")
            return False
    except Exception as e:
        logger.error(f"❌ 视觉分析失败: {e}")
        return False

async def main():
    """主测试函数"""
    logger.info("=" * 60)
    logger.info("🚀 Kimi API 测试")
    logger.info("=" * 60)
    
    results = {
        "kimi_standard": await test_kimi_standard(),
        "kimi_coding": await test_kimi_coding(),
        "kimi_vision": await test_kimi_vision()
    }
    
    logger.info("\n" + "=" * 60)
    logger.info("📊 测试结果汇总")
    logger.info("=" * 60)
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        logger.info(f"{test_name}: {status}")
    
    passed = sum(results.values())
    total = len(results)
    logger.info(f"\n总计: {passed}/{total} 项测试通过")

if __name__ == "__main__":
    asyncio.run(main())

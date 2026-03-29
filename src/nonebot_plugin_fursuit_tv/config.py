from pydantic import BaseModel
from typing import Optional


class FurtvConfig(BaseModel):
    """Furtv 插件配置"""
    ftv_base_url: str = "https://open-cn1.vdsentnet.com"
    # 动态令牌获取所需配置
    app_id: str = ""
    client_secret: str = ""


# 全局配置实例（将在 __init__.py 中初始化）
ftv_config: Optional[FurtvConfig] = None


def get_ftv_config() -> FurtvConfig:
    """获取插件配置"""
    global ftv_config
    if ftv_config is None:
        ftv_config = FurtvConfig()
    return ftv_config

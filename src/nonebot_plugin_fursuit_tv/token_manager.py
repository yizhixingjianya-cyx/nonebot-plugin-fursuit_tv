"""
FurtvAPI Token Manager
负责管理 API 令牌的获取、刷新和使用
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from loguru import logger

from .config import get_ftv_config


class TokenManager:
    """令牌管理器 - 统一管理签名获取和刷新"""
    
    def __init__(self):
        self._api_key: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._refresh_window = timedelta(seconds=300)  # 5 分钟刷新窗口
        self._lock = asyncio.Lock()
        self._initialized = False
        self._grants: list = []  # 权限组列表
        
    async def initialize(self) -> bool:
        """初始化令牌（首次获取）"""
        if self._initialized:
            logger.debug("令牌已初始化，跳过")
            return True
            
        async with self._lock:
            if self._initialized:
                logger.debug("令牌已在锁内初始化，跳过")
                return True
            
            config = get_ftv_config()
            
            # 使用动态令牌模式
            if config.app_id and config.client_secret:
                logger.info(f"开始获取令牌 | 端点：{config.ftv_base_url} | appId: {config.app_id}")
                try:
                    await self._exchange_token(config.app_id, config.client_secret)
                    self._initialized = True
                    logger.success(f"令牌初始化成功 | apiKey: {self._api_key[:20]}... | 过期时间：{self._expires_at} | 权限组：{self._grants}")
                    return True
                except Exception as e:
                    logger.error(f"令牌获取失败 | 错误：{e}")
                    return False
            else:
                logger.warning("未配置 API 令牌 | 需要设置：app_id 和 client_secret")
                return False
    
    async def get_api_key(self) -> Optional[str]:
        """获取 API Key（自动刷新）"""
        if not await self.initialize():
            logger.warning("获取 API Key 失败：初始化未完成")
            return None
        
        # 检查是否需要刷新
        if self._needs_refresh():
            logger.info("令牌即将过期，开始刷新...")
            await self._refresh_token()
        
        if self._api_key:
            logger.debug(f"返回 API Key: {self._api_key[:20]}... | 过期时间：{self._expires_at}")
        else:
            logger.error("API Key 为空")
        
        return self._api_key
    
    def _needs_refresh(self) -> bool:
        """检查是否需要刷新令牌"""
        if self._expires_at is None:
            logger.debug("令牌未设置，需要刷新")
            return True
        
        # 剩余时间小于刷新窗口时需要刷新
        remaining = self._expires_at - datetime.now()
        needs_refresh = remaining <= self._refresh_window
        
        if needs_refresh:
            logger.info(f"令牌检查 | 剩余时间：{remaining.total_seconds():.0f}秒 | 刷新窗口：{self._refresh_window.total_seconds():.0f}秒 | 需要刷新")
        else:
            logger.debug(f"令牌检查 | 剩余时间：{remaining.total_seconds():.0f}秒 | 无需刷新")
        
        return needs_refresh
    
    async def _refresh_token(self):
        """刷新令牌"""
        logger.info("开始刷新令牌...")
        try:
            config = get_ftv_config()
            
            # 调用签名交换接口
            if hasattr(config, 'app_id') and hasattr(config, 'client_secret'):
                logger.info(f"刷新令牌 | 端点：{config.ftv_base_url} | appId: {config.app_id}")
                await self._exchange_token(config.app_id, config.client_secret)
                logger.success(f"令牌刷新成功 | apiKey: {self._api_key[:20]}... | 新过期时间：{self._expires_at}")
            else:
                logger.error("刷新失败：缺少 app_id 或 client_secret 配置")
        except Exception as e:
            logger.error(f"刷新令牌失败 | 错误：{e}")
            raise
    
    async def check_and_refresh(self):
        """定时检查并刷新令牌（由 APScheduler 调用）"""
        if not self._initialized:
            logger.debug("令牌未初始化，跳过检查")
            return
        
        if self._needs_refresh():
            logger.info("定时检查发现令牌即将过期，开始刷新...")
            try:
                await self._refresh_token()
                logger.success("定时刷新成功")
            except Exception as e:
                logger.error(f"定时刷新失败：{e}")
        else:
            logger.debug("定时检查：令牌状态正常")
    
    async def auto_refresh_loop(self):
        """后台自动刷新循环（已废弃，使用 APScheduler）"""
        logger.warning("auto_refresh_loop 已废弃，请使用 APScheduler")
    
    async def _exchange_token(self, app_id: str, client_secret: str):
        """调用签名交换接口获取新令牌"""
        import httpx
        
        config = get_ftv_config()
        url = f"{config.ftv_base_url}/api/auth/token"
        
        logger.info(f"请求令牌接口 | URL: {url} | appId: {app_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                logger.debug(f"发送 POST 请求 | 超时：30s")
                response = await client.post(
                    url,
                    json={
                        "appId": app_id,
                        "clientSecret": client_secret
                    },
                    timeout=30.0
                )
                
                logger.debug(f"收到响应 | 状态码：{response.status_code}")
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"响应数据 | accessToken: {data.get('accessToken', '')[:20]}... | apiKey: {data.get('apiKey', '')[:20]}... | expiresInSeconds: {data.get('expiresInSeconds')} | grants: {data.get('grants')}")
                
                self._update_tokens(data)
                logger.success(f"令牌获取成功 | apiKey: {self._api_key[:20]}... | 过期时间：{self._expires_at}")
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP 错误 | 状态码：{e.response.status_code} | 响应：{e.response.text[:200]}")
            raise
        except httpx.RequestError as e:
            logger.error(f"网络请求错误 | 错误：{e}")
            raise
        except Exception as e:
            logger.error(f"签名交换失败 | 错误类型：{type(e).__name__} | 错误：{e}")
            raise
    

    
    def _update_tokens(self, data: Dict[str, Any]):
        """更新令牌信息"""
        self._api_key = data.get('apiKey')
        
        expires_in = data.get('expiresInSeconds', 3600)
        self._expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # 更新权限组列表
        self._grants = data.get('grants', [])
        
        logger.info(f"令牌已更新 | apiKey: {self._api_key[:20]}... | 有效期：{expires_in}秒 | 过期时间：{self._expires_at.strftime('%Y-%m-%d %H:%M:%S')} | 权限组：{self._grants}")
    
    def has_grant(self, grant: str) -> bool:
        """检查是否有指定权限
        
        Args:
            grant: 权限名称，如 'furtv', 'furtv.gatherings'
        
        Returns:
            bool: 是否有该权限
        """
        if not self._grants:
            return False
        
        # 精确匹配
        if grant in self._grants:
            return True
        
        # 检查通配符权限（如 'furtv' 匹配 'furtv.*'）
        for g in self._grants:
            if g == grant.split('.')[0]:  # 例如 'furtv' 匹配 'furtv.gatherings'
                return True
            if g.startswith(grant + '.'):  # 例如 'furtv.gatherings' 匹配 'furtv.gatherings.timeline'
                return True
        
        return False
    
    def get_grants(self) -> list:
        """获取当前权限组列表"""
        return self._grants.copy()
    
    def check_grants_and_log(self, required_grants: list, operation: str = "操作"):
        """检查权限并记录日志
        
        Args:
            required_grants: 需要的权限列表
            operation: 操作描述
        
        Returns:
            bool: 是否有足够的权限
        """
        missing_grants = [g for g in required_grants if not self.has_grant(g)]
        
        if missing_grants:
            logger.warning(f"权限不足 | 操作：{operation} | 缺少权限：{missing_grants} | 当前权限：{self._grants}")
            return False
        else:
            logger.debug(f"权限检查通过 | 操作：{operation} | 所需权限：{required_grants} | 当前权限：{self._grants}")
            return True
    
    def get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头"""
        headers = {'Content-Type': 'application/json'}
        
        if self._api_key:
            headers['X-Api-Key'] = self._api_key
            logger.debug(f"生成认证头 | X-Api-Key: {self._api_key[:20]}...")
        else:
            logger.warning("生成认证头失败：API Key 为空")
        
        return headers


# 创建全局 Token Manager 实例
token_manager = TokenManager()


# 创建全局 Token Manager 实例
token_manager = TokenManager()

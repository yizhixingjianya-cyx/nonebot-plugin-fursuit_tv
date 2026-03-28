import httpx
from typing import Optional, Dict, Any
from .config import get_ftv_config, FurtvConfig
from .token_manager import token_manager
from .cache_manager import get_cache_manager
from loguru import logger


def check_api_grant(required_grant: str, operation: str) -> bool:
    """检查 API 权限
    
    Args:
        required_grant: 需要的权限，如 'furtv', 'furtv.gatherings'
        operation: 操作描述
    
    Returns:
        bool: 是否有权限
    """
    if not token_manager._initialized:
        logger.warning(f"令牌未初始化，无法检查权限 | 操作：{operation}")
        return False
    
    return token_manager.check_grants_and_log([required_grant], operation)


class FurtvAPI:
    """Furtv API 客户端"""
    
    def __init__(self):
        self._config: Optional[FurtvConfig] = None
    
    @property
    def config(self) -> FurtvConfig:
        """延迟获取配置"""
        if self._config is None:
            self._config = get_ftv_config()
        return self._config
    
    @property
    def base_url(self) -> str:
        return self.config.ftv_base_url
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头，使用 Token Manager 管理"""
        return token_manager.get_auth_headers()
    
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, required_grant: Optional[str] = None, operation: Optional[str] = None, use_cache: bool = True, log_response: bool = True) -> Dict[str, Any]:
        """发起 HTTP 请求
        
        Args:
            method: HTTP 方法
            endpoint: API 端点
            params: 请求参数
            required_grant: 所需权限（可选），如 'furtv.gatherings'
            operation: 操作描述（可选），用于日志
            use_cache: 是否使用缓存（默认 True）
            log_response: 是否记录响应日志（默认 True）
        
        Returns:
            响应数据
        """
        # 检查权限
        if required_grant:
            op_desc = operation or f"访问 {endpoint}"
            if not check_api_grant(required_grant, op_desc):
                logger.error(f"❌ 权限不足，拒绝请求 | 端点：{endpoint} | 所需权限：{required_grant} | 操作：{op_desc}")
                raise PermissionError(f"权限不足：{required_grant} | 操作：{op_desc}")
        
        # 尝试从缓存获取（仅 GET 请求）
        if use_cache and method == 'GET':
            try:
                cache = get_cache_manager()
                if cache:
                    cached_data = await cache.get(endpoint, params)
                    if cached_data:
                        logger.info(f"✅ 使用缓存 | 端点：{endpoint}")
                        return cached_data
            except Exception as e:
                logger.warning(f"读取缓存失败，将直接请求：{e}")
        
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                timeout=30.0
            )
            
            # 处理 404 错误
            if response.status_code == 404:
                request_id = response.headers.get('x-request-id', 'unknown')
                logger.warning(f"⚠️ 资源未找到 | 操作：{operation or f'访问 {endpoint}'} | 端点：{endpoint} | 状态码：404 | requestId: {request_id}")
                raise FileNotFoundError(f"资源未找到：{endpoint}")
            
            response.raise_for_status()
            data = response.json()
            
            # 记录 requestId
            request_id = response.headers.get('x-request-id', data.get('requestId', 'unknown'))
            
            # 记录响应日志
            if log_response:
                self._log_response(endpoint, operation, data, request_id)
            
            # 保存到缓存（仅 GET 请求）
            if use_cache and method == 'GET':
                try:
                    cache = get_cache_manager()
                    if cache:
                        await cache.set(endpoint, params, data)
                except Exception as e:
                    logger.warning(f"保存缓存失败：{e}")
            
            return data
    
    def _log_response(self, endpoint: str, operation: Optional[str], data: Dict, request_id: str):
        """记录响应日志
        
        Args:
            endpoint: API 端点
            operation: 操作描述
            data: 响应数据
            request_id: 请求 ID
        """
        import json
        
        op_desc = operation or f"访问 {endpoint}"
        
        # 检查响应是否成功
        code = data.get('code', 200)
        message = data.get('message', 'Success')
        
        if code != 200:
            logger.error(f"❌ API 返回错误 | 操作：{op_desc} | 端点：{endpoint} | 状态码：{code} | 错误：{message} | requestId: {request_id}")
            logger.error(f"完整响应：{json.dumps(data, ensure_ascii=False, indent=2)}")
            return
        
        # 提取关键数据记录日志（支持多种返回结构）
        data_content = None
        content_type = None
        
        # 用户相关
        if 'users' in data:
            data_content = data.get('users')
            content_type = 'users'
        elif 'user' in data:
            data_content = data.get('user')
            content_type = 'user'
        elif 'fursuit' in data:
            data_content = data.get('fursuit')
            content_type = 'fursuit'
        elif 'fursuits' in data:
            data_content = data.get('fursuits')
            content_type = 'fursuits'
        elif 'relationships' in data:
            data_content = data.get('relationships')
            content_type = 'relationships'
        elif 'visitors' in data:
            data_content = data.get('visitors')
            content_type = 'visitors'
        elif 'badges' in data:
            data_content = data.get('badges')
            content_type = 'badges'
        elif 'badge' in data:
            data_content = data.get('badge')
            content_type = 'badge'
        elif 'products' in data:
            data_content = data.get('products')
            content_type = 'products'
        elif 'characters' in data:
            data_content = data.get('characters')
            content_type = 'characters'
        # 聚会相关
        elif 'gathering' in data:
            data_content = data.get('gathering')
            content_type = 'gathering'
        elif 'registrations' in data:
            data_content = data.get('registrations')
            content_type = 'registrations'
        elif 'gatherings' in data:
            data_content = data.get('gatherings')
            content_type = 'gatherings'
        # 学校相关
        elif 'school' in data:
            data_content = data.get('school')
            content_type = 'school'
        elif 'schools' in data:
            data_content = data.get('schools')
            content_type = 'schools'
        # 地区和物种
        elif 'popular_provinces' in data:
            data_content = data.get('popular_provinces')
            content_type = 'popular_provinces'
        elif 'species' in data:
            data_content = data.get('species')
            content_type = 'species'
        # 主题包
        elif 'data' in data:
            data_content = data.get('data')
            content_type = 'data'
            # 检查是否有嵌套的 packs 或 gatherings
            if isinstance(data_content, dict):
                if 'packs' in data_content:
                    data_content = data_content.get('packs')
                    content_type = 'packs'
                elif 'gatherings' in data_content:
                    data_content = data_content.get('gatherings')
                    content_type = 'gatherings'
        
        if isinstance(data_content, list):
            count = len(data_content)
            if count > 0:
                # 记录列表项的关键信息
                if data_content and isinstance(data_content[0], dict):
                    # 尝试提取常见字段
                    names = [item.get('name', item.get('nickname', item.get('username', item.get('title', item.get('species', '未知'))))) for item in data_content[:5]]
                    logger.info(f"{op_desc} | 端点：{endpoint} | 数量：{count} | 示例：{', '.join(names)} | requestId: {request_id}")
                else:
                    logger.info(f"{op_desc} | 端点：{endpoint} | 数量：{count} | requestId: {request_id}")
            else:
                logger.warning(f"{op_desc} | 端点：{endpoint} | 返回空列表 | requestId: {request_id}")
        
        elif isinstance(data_content, dict):
            # 记录字典类型的关键信息
            name = data_content.get('name', data_content.get('nickname', data_content.get('id', '未知')))
            logger.info(f"{op_desc} | 端点：{endpoint} | 数据：{name} | requestId: {request_id}")
        
        elif data_content is None:
            logger.warning(f"{op_desc} | 端点：{endpoint} | 无数据内容 | requestId: {request_id}")
        
        else:
            logger.debug(f"{op_desc} | 端点：{endpoint} | requestId: {request_id}")
        
        # 打印完整响应（info 级别）
        logger.info(f"完整响应数据 | 操作：{op_desc}:\n{json.dumps(data, ensure_ascii=False, indent=2)}")
    
    # 发现与搜索 - 推荐能力
    async def get_popular(self, limit: int = 10):
        """获取热门推荐档案（不缓存）"""
        return await self._request('GET', '/api/proxy/furtv/popular', {'limit': limit}, 'furtv.discovery', '获取热门推荐', use_cache=False)
    
    async def get_random(self, count: int = 1):
        """获取随机推荐档案（不缓存）"""
        return await self._request('GET', '/api/proxy/furtv/fursuit/random', {'count': count}, 'furtv.fursuit', '获取随机推荐', use_cache=False)
    
    # 发现与搜索 - 检索能力
    async def search_by_species(self, species: str, page: int = 1, limit: int = 20, cursor: Optional[str] = None):
        """按物种搜索公开档案"""
        params = {'page': page, 'limit': limit}
        if cursor:
            params['cursor'] = cursor
        return await self._request('GET', f'/api/proxy/furtv/search/species/{species}', params, 'furtv.discovery', f'搜索物种：{species}')
    
    async def search(self, q: str, type: str = 'all', page: int = 1, limit: int = 20, cursor: Optional[str] = None):
        """按关键词搜索公开档案"""
        params = {'q': q, 'type': type, 'page': page, 'limit': limit}
        if cursor:
            params['cursor'] = cursor
        return await self._request('GET', '/api/proxy/furtv/search', params, 'furtv.discovery', f'搜索关键词：{q}')
    
    async def get_popular_locations(self):
        """获取热门地区统计"""
        return await self._request('GET', '/api/proxy/furtv/locations/popular', None, 'furtv.discovery', '获取热门地区')
    
    async def get_species_list(self):
        """获取物种统计列表"""
        return await self._request('GET', '/api/proxy/furtv/species', None, 'furtv.discovery', '获取物种列表')
    
    # 基础能力 - 主题资源
    async def get_theme_packs_manifest(self):
        """获取主题包清单"""
        return await self._request('GET', '/api/proxy/furtv/theme-packs/manifest', 'furtv.themepacks', '获取主题包清单')
    
    # 学校与角色 - 学校
    async def search_schools(self, query: str):
        """按名称搜索学校"""
        return await self._request('GET', '/api/proxy/furtv/schools/search', {'query': query}, 'furtv.schools', f'搜索学校：{query}')
    
    async def get_school_detail(self, school_id: str):
        """获取学校详情"""
        return await self._request('GET', f'/api/proxy/furtv/schools/{school_id}', None, 'furtv.schools', f'获取学校详情：{school_id}')
    
    async def get_user_school_info(self, user_id: str):
        """获取用户学校信息"""
        return await self._request('GET', f'/api/proxy/furtv/schools/user/{user_id}', None, 'furtv.schools', f'获取用户学校信息：{user_id}')
    
    # 学校与角色 - 角色
    async def get_user_characters(self, username: str):
        """获取用户角色列表"""
        return await self._request('GET', f'/api/proxy/furtv/characters/user/{username}', None, 'furtv.characters', f'获取用户角色：{username}')
    
    # 用户公开资料 - 基础信息
    async def get_user_info_by_id(self, user_id: str):
        """通过用户 ID 获取公开基础资料"""
        return await self._request('GET', f'/api/proxy/furtv/users/id/{user_id}', None, 'furtv.users', f'获取用户信息：{user_id}')
    
    async def get_user_like_status(self, username: str):
        """查询用户点赞状态"""
        return await self._request('GET', f'/api/proxy/furtv/fursuit/like-status/{username}', None, 'furtv.fursuit', f'查询点赞状态：{username}')
    
    async def get_user_profile(self, username: str):
        """获取用户公开资料"""
        return await self._request('GET', f'/api/proxy/furtv/users/{username}', None, 'furtv.users', f'获取用户资料：{username}')
    
    # 用户公开资料 - 关系与访客
    async def get_user_relationships(self, user_id: str):
        """获取用户关系公开列表"""
        return await self._request('GET', f'/api/proxy/furtv/relationships/user/{user_id}', None, 'furtv.relationships', f'获取用户关系：{user_id}')
    
    async def get_user_visitors(self, username: str):
        """获取用户访客记录"""
        return await self._request('GET', f'/api/proxy/furtv/users/{username}/visitors', None, 'furtv.users', f'获取访客记录：{username}')
    
    # 用户公开资料 - 徽章与商店
    async def get_user_social_badges(self, username: str, limit: int = 50):
        """获取用户社交徽章列表"""
        return await self._request('GET', f'/api/proxy/furtv/users/{username}/social-badges', {'limit': limit}, 'furtv.users', f'获取社交徽章：{username}')
    
    async def get_user_social_badge_detail(self, username: str, user_badge_id: str):
        """获取单个社交徽章详情"""
        return await self._request('GET', f'/api/proxy/furtv/users/{username}/social-badges/{user_badge_id}', None, 'furtv.users', f'获取徽章详情：{user_badge_id}')
    
    async def get_user_store_products(self, username: str):
        """获取用户已上架商品列表"""
        return await self._request('GET', f'/api/proxy/furtv/users/{username}/store-products', None, 'furtv.users', f'获取商店商品：{username}')
    
    # 聚会 - 列表与统计
    async def get_gatherings_yearly_stats(self):
        """获取当前年份聚会总数"""
        return await self._request('GET', '/api/proxy/furtv/gatherings/stats/this-year', None, 'furtv.gatherings', '获取聚会年度统计')
    
    async def get_gatherings_monthly(self, year: int, month: int):
        """按月份返回聚会列表"""
        return await self._request('GET', '/api/proxy/furtv/gatherings/monthly', {'year': year, 'month': month}, 'furtv.gatherings', f'获取{year}年{month}月聚会')
    
    async def get_gatherings_monthly_distance(self, year: int, month: int, lat: float, lng: float):
        """按月份返回聚会距离"""
        params = {'year': year, 'month': month, 'lat': lat, 'lng': lng}
        return await self._request('GET', '/api/proxy/furtv/gatherings/monthly-distance', params, 'furtv.gatherings', f'获取{year}年{month}月聚会距离')
    
    async def get_gatherings_nearby(self):
        """返回附近聚会坐标"""
        return await self._request('GET', '/api/proxy/furtv/gatherings/nearby', None, 'furtv.gatherings', '获取附近聚会')
    
    async def get_gatherings_nearby_mode(self):
        """返回附近聚会及用户意向"""
        return await self._request('GET', '/api/proxy/furtv/gatherings/nearby-mode', None, 'furtv.gatherings', '获取附近聚会模式')
    
    # 聚会 - 详情与报名
    async def get_gathering_detail(self, gathering_id: str):
        """获取聚会详情"""
        return await self._request('GET', f'/api/proxy/furtv/gatherings/{gathering_id}', None, 'furtv.gatherings', f'获取聚会详情：{gathering_id}')
    
    async def get_gathering_registrations(self, gathering_id: str):
        """获取聚会报名列表"""
        return await self._request('GET', f'/api/proxy/furtv/gatherings/{gathering_id}/registrations', None, 'furtv.gatherings', f'获取聚会报名：{gathering_id}')


# 创建全局 API 实例
furtv_api = FurtvAPI()

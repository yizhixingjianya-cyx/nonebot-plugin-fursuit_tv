from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.typing import T_State
from io import BytesIO
from nonebot.exception import FinishedException
from .api import furtv_api, check_api_grant
from .config import get_ftv_config
from .image_generator import generate_profile_image
from .token_manager import token_manager
from .cache_manager import get_cache_manager
from datetime import datetime
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent


def format_user_info(item: dict) -> str:
    """格式化用户信息为文本
    
    Args:
        item: 用户数据字典
    
    Returns:
        格式化后的文本
    """
    # 基本信息
    name = item.get('nickname', item.get('username', '未知'))
    username = item.get('username', '')
    species = item.get('fursuit_species', '未知物种')
    location = item.get('location', '未知地区')
    
    # 构建文本
    text = f"{name}\n"
    
    # 添加用户名（如果有且与昵称不同）
    if username and username != name:
        text += f"ID: {username}\n"
    
    # 添加物种
    text += f"物种：{species}\n"
    
    # 添加地区
    text += f"地区：{location}\n"
    
    # 添加兽装制作人（如果有）
    maker = item.get('fursuit_maker')
    if maker:
        text += f"兽装制作：{maker}\n"
    
    # 添加浏览量（如果有）
    view_count = item.get('view_count')
    if view_count is not None:
        text += f"浏览：{view_count}\n"
    
    # 添加简介（如果有）
    introduction = item.get('introduction')
    if introduction:
        # 简介太长就截断
        if len(introduction) > 50:
            introduction = introduction[:47] + "..."
        text += f"简介：{introduction}\n"
    
    # 添加联系方式（如果有）
    contact_info = item.get('contact_info')
    if contact_info:
        qq = contact_info.get('qq')
        if qq:
            text += f"QQ: {qq}\n"
    
    # 添加创建时间（转换为日期）
    created_at = item.get('created_at')
    if created_at:
        try:
            # 解析 ISO 8601 格式
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d')
            text += f"加入：{date_str}\n"
        except:
            pass
    
    return text


async def send_image_with_text(cmd, image_url: str = None, image_bytes: BytesIO = None, text: str = "", title: str = ""):
    """发送图片和文本
    
    Args:
        cmd: 命令处理器
        image_url: 图片 URL
        image_bytes: 图片字节流
        text: 文本内容
        title: 标题（用于合并转发）
    """
    if image_url:
        msg = Message([
            MessageSegment.image(image_url),
            MessageSegment.text(f"\n{text}")
        ])
        return await cmd.finish(msg)
    elif image_bytes:
        msg = Message([
            MessageSegment.image(image_bytes),
            MessageSegment.text(f"\n{text}")
        ])
        return await cmd.finish(msg)
    else:
        return await cmd.finish(text)


async def send_forward_message(cmd, event: MessageEvent, items: list, title: str = ""):
    """发送合并转发消息（2 条以上）
    
    Args:
        cmd: 命令处理器
        event: 消息事件
        items: 列表项，每项包含 image_url/image_bytes 和 text
        title: 标题
    """
    if not items:
        return
    
    # 如果只有 1 项，直接发送
    if len(items) == 1:
        item = items[0]
        await send_image_with_text(cmd, item.get('image_url'), item.get('image_bytes'), item.get('text', ''))
        return
    
    # 2 项以上使用合并转发
    from nonebot.adapters.onebot.v11 import MessageSegment
    from nonebot import get_bot
    from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
    
    # 获取 Bot 对象
    bot = get_bot()
    
    messages = []
    for i, item in enumerate(items, 1):
        # 构建消息内容（使用消息段数组）
        content = []
        if item.get('image_url'):
            content.append(MessageSegment.image(item['image_url']))
        elif item.get('image_bytes'):
            content.append(MessageSegment.image(item['image_bytes']))
        if item.get('text'):
            content.append(MessageSegment.text(item['text']))
        
        messages.append({
            "type": "node",
            "data": {
                "user_id": bot.self_id,
                "nickname": "CYX-FURSUIT-TV",
                "content": content
            }
        })
    
    # 根据消息类型使用不同的 API
    if isinstance(event, GroupMessageEvent):
        # 群聊合并转发
        await bot.send_group_forward_msg(group_id=event.group_id, messages=messages)
    elif isinstance(event, PrivateMessageEvent):
        # 私聊合并转发
        await bot.send_private_forward_msg(user_id=event.user_id, messages=messages)
    
    # 结束命令（不发送额外消息）
    await cmd.finish()


# 初始化配置
config = get_ftv_config()

# 帮助命令(AI原来写的窝补药)





# 热门推荐命令
popular_cmd = on_command("热门", aliases={"热门推荐"}, priority=5, block=True)#没问题


@popular_cmd.handle()
async def _(event: MessageEvent, state: T_State, arg: Message = CommandArg()):
    limit = 10
    if arg.extract_plain_text().strip():
        try:
            limit = int(arg.extract_plain_text().strip())
            limit = max(1, min(limit, 50))
        except ValueError:
            pass
    
    try:
        data = await furtv_api.get_popular(limit)
        
        # 支持多种返回结构
        popular_list = None
        if 'users' in data:
            popular_list = data.get('users', [])
        elif 'fursuits' in data:
            popular_list = data.get('fursuits', [])
        elif 'fursuit' in data:
            popular_list = [data.get('fursuit', {})]
        elif 'data' in data:
            popular_list = data.get('data', [])
        
        if not popular_list:
            await popular_cmd.finish("暂无热门推荐")
        
        # 构建消息列表
        items = []
        for item in popular_list:
            avatar_url = item.get('avatar_url')
            
            # 使用格式化函数
            text = format_user_info(item)
            
            items.append({
                'image_url': avatar_url,
                'text': text
            })
        
        # 使用合并转发或单条消息
        await send_forward_message(popular_cmd, event, items, "推荐档案")
        return await popular_cmd.finish()
        
    except PermissionError as e:
        await popular_cmd.finish(f"端点权限不足，请联系 bot 管理员：{str(e)}")
    except FileNotFoundError as e:
        await popular_cmd.finish(f"资源未找到：{str(e)}")
    except FinishedException:
        # 已经发送过消息，无需处理
        pass
    except Exception as e:
        await popular_cmd.finish(f"获取失败：{str(e)}")


# 随机推荐命令
random_cmd = on_command("随机", aliases={"随机档案"}, priority=5, block=True)#莫得问题


@random_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    count = 1
    if arg.extract_plain_text().strip():
        try:
            count = int(arg.extract_plain_text().strip())
            count = max(1, min(count, 20))
        except ValueError:
            pass
    
    try:
        data = await furtv_api.get_random(count)
        
        # 支持多种返回结构
        random_list = None
        if 'fursuit' in data:
            # 单个 fursuit 对象，转为列表
            random_list = [data.get('fursuit', {})]
        elif 'data' in data:
            random_list = data.get('data', [])
        
        if not random_list:
            await random_cmd.finish("暂无随机推荐")
        
        # 构建消息列表
        items = []
        for item in random_list:
            avatar_url = item.get('avatar_url')
            
            # 使用格式化函数
            text = format_user_info(item)
            
            items.append({
                'image_url': avatar_url,
                'text': text
            })
        
        # 使用合并转发或单条消息
        await send_forward_message(random_cmd, event, items, "随机档案")
        return await random_cmd.finish()
        
    except PermissionError as e:
        await random_cmd.finish(f"权限不足：{str(e)}")
    except FileNotFoundError as e:
        await random_cmd.finish(f"没有该数据")
    except FinishedException:
        pass
    except Exception as e:
        await random_cmd.finish(f"获取失败：{str(e)}")


# 物种搜索命令
species_cmd = on_command("物种", aliases={"物种搜索"}, priority=5, block=True)


@species_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip().split()
    if not args:
        await species_cmd.finish("请提供物种名称，例如：.物种 狼")
    
    species = args[0]
    page = 1
    if len(args) > 1:
        try:
            page = int(args[1])
        except ValueError:
            pass
    
    try:
        data = await furtv_api.search_by_species(species, page=page)
        
        # 支持多种返回结构
        result_list = None
        if 'users' in data:
            result_list = data.get('users', [])
        elif 'data' in data:
            result_list = data.get('data', [])
        
        if not result_list:
            await species_cmd.finish(f"未找到物种 '{species}' 的相关档案")
        
        # 构建消息列表
        items = []
        for i, item in enumerate(result_list[:10], 1):
            avatar_url = item.get('avatar_url')
            
            # 使用格式化函数
            text = format_user_info(item)
            
            items.append({
                'image_url': avatar_url,
                'text': text
            })
        
        # 使用合并转发或单条消息
        await send_forward_message(species_cmd, event, items, f"物种'{species}'搜索")
        return await species_cmd.finish()
        
    except PermissionError as e:
        await species_cmd.finish(f"端点权限不足，请联系 bot 管理员{str(e)}")
    except FileNotFoundError as e:
        await species_cmd.finish(f"没有该数据")
    except FinishedException:
        pass
    except Exception as e:
        await species_cmd.finish(f"搜索失败：{str(e)}")


# 关键词搜索命令
search_cmd = on_command("搜索", aliases={"兽搜索"}, priority=5, block=True)#没问题


@search_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip().split()
    if not args:
        await search_cmd.finish("请提供搜索关键词，例如：.搜索 毛毛")
    
    q = args[0]
    search_type = 'all'
    if len(args) > 1:
        search_type = args[1]
    
    try:
        data = await furtv_api.search(q, type=search_type)
        
        # 支持多种返回结构：{'users': [...]} 或 {'data': [...]}
        result_list = None
        if 'users' in data:
            result_list = data.get('users', [])
        elif 'data' in data:
            result_list = data.get('data', [])
        
        if not result_list:
            await search_cmd.finish(f"未找到关键词 '{q}' 的相关结果")
        
        # 构建消息列表
        items = []
        for i, item in enumerate(result_list[:10], 1):
            avatar_url = item.get('avatar_url')
            
            # 使用格式化函数
            text = format_user_info(item)
            
            items.append({
                'image_url': avatar_url,
                'text': text
            })
        
        # 使用合并转发或单条消息
        await send_forward_message(search_cmd, event, items, f"关键词'{q}'搜索")
        return await search_cmd.finish()
        
    except PermissionError as e:
        await search_cmd.finish(f"权限不足：{str(e)}")
    except FileNotFoundError as e:
        await search_cmd.finish(f"没有该数据")
    except FinishedException:
        pass
    except Exception as e:
        await search_cmd.finish(f"搜索失败：{str(e)}")


# 热门地区命令
locations_cmd = on_command("热门地区", priority=5, block=True)


@locations_cmd.handle()
async def _(event: MessageEvent):
    try:
        data = await furtv_api.get_popular_locations()
        
        # 支持多种返回结构
        locations = None
        if 'popular_cities' in data:
            locations = data.get('popular_cities', [])
        elif 'popular_provinces' in data:
            locations = data.get('popular_provinces', [])
        elif 'data' in data:
            locations = data.get('data', [])
        
        if not locations:
            await locations_cmd.finish("暂无热门地区数据")
        
        # 显示总用户数
        total_users = data.get('total_users', 0)
        
        # 每 20 个地区一条消息，使用合并转发
        items = []
        batch_size = 20
        
        # 添加总用户数作为第一条
        items.append({
            'image_url': None,
            'text': f"热门地区统计\n\n总用户数：{total_users}"
        })
        
        # 分批处理地区数据
        for i in range(0, len(locations), batch_size):
            batch = locations[i:i + batch_size]
            text = f"热门地区 ({i+1}-{min(i+batch_size, len(locations))})\n\n"
            for j, loc in enumerate(batch, 1):
                # 支持省份和城市两种格式
                if 'province' in loc and 'city' in loc:
                    # 城市格式
                    name = f"{loc.get('province', '')}{loc.get('city', '')}"
                else:
                    # 省份格式
                    name = loc.get('province', '未知')
                count = loc.get('count', 0)
                text += f"{i+j}. {name}: {count}个档案\n"
            
            items.append({
                'image_url': None,
                'text': text
            })
        
        # 使用合并转发
        await send_forward_message(locations_cmd, event, items, "热门地区")
        return await locations_cmd.finish()
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await locations_cmd.finish(f"没有该数据")
    except Exception as e:
        await locations_cmd.finish(f"获取失败：{str(e)}")


# 物种列表命令
species_list_cmd = on_command("物种列表", priority=5, block=True)


@species_list_cmd.handle()
async def _(event: MessageEvent):
    try:
        data = await furtv_api.get_species_list()
        
        # 支持多种返回结构
        species_list = None
        if 'species' in data:
            species_list = data.get('species', [])
        elif 'data' in data:
            species_list = data.get('data', [])
        
        if not species_list:
            await species_list_cmd.finish("暂无物种数据")
        
        # 每 20 个物种一条消息，使用合并转发
        items = []
        batch_size = 20
        
        # 分批处理
        for i in range(0, len(species_list), batch_size):
            batch = species_list[i:i + batch_size]
            text = f"物种统计列表 ({i+1}-{min(i+batch_size, len(species_list))})\n\n"
            for j, species in enumerate(batch, 1):
                name = species.get('species', '未知')
                count = species.get('count', 0)
                text += f"{i+j}. {name}: {count}个档案\n"
            
            items.append({
                'image_url': None,
                'text': text
            })
        
        # 使用合并转发
        await send_forward_message(species_list_cmd, event, items, "物种统计")
        return await species_list_cmd.finish()
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await species_list_cmd.finish(f"没有该数据")
    except Exception as e:
        await species_list_cmd.finish(f"获取失败：{str(e)}")


# 学校搜索命令
school_cmd = on_command("学校", aliases={"学校搜索"}, priority=5, block=True)


@school_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    query = arg.extract_plain_text().strip()
    if not query:
        await school_cmd.finish("请提供学校名称，例如：.学校 北京大学")
    
    try:
        data = await furtv_api.search_schools(query)
        
        # 支持多种返回结构
        schools = None
        if 'schools' in data:
            schools = data.get('schools', [])
        elif 'data' in data:
            schools = data.get('data', [])
        
        if not schools:
            await school_cmd.finish(f"未找到学校 '{query}'")
        
        result = f"学校搜索结果：'{query}'\n\n"
        for i, school in enumerate(schools[:10], 1):
            name = school.get('name', '未知')
            location = school.get('location', '未知地区')
            result += f"{i}. {name} - {location}\n"
        
        await school_cmd.finish(result)
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await school_cmd.finish(f"没有该数据（{query}），请尝试输入全名或 ID")
    except Exception as e:
        await school_cmd.finish(f"搜索失败：{str(e)}")


# 用户资料命令
user_profile_cmd = on_command("兽档案", aliases={"用户信息"}, priority=5, block=True)#没问题


@user_profile_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    username = arg.extract_plain_text().strip()
    if not username:
        await user_profile_cmd.finish("请提供用户名，例如：.用户资料 example")
    
    try:
        data = await furtv_api.get_user_profile(username)
        
        # 支持多种返回结构
        user = None
        if 'user' in data:
            user = data.get('user', {})
        elif 'data' in data:
            user = data.get('data', {})
        
        if not user:
            await user_profile_cmd.finish(f"未找到用户 '{username}'")
        
        # 使用图片生成器生成档案图片
        profile_data = {
            "id": user.get('id', username),
            "nickname": user.get('nickname', '未知昵称'),
            "username": user.get('username', username),
            "fursuit_species": user.get('fursuit_species', '未知'),
            "fursuit_birthday": user.get('fursuit_birthday', '无'),
            "fursuit_maker": user.get('fursuit_maker', '未知'),
            "location": user.get('location', '未知'),
            "introduction": user.get('introduction', '无'),
            "interests": user.get('interests', [])
        }
        
        # 获取图片 URL（使用正确的字段）
        avatar_url = user.get('avatar_url', 'https://picsum.photos/id/101/200/200')
        vertical_img_url = user.get('showcase_portrait', 'https://picsum.photos/id/100/800/1600')  # 竖向 1080*1920
        horizontal_img_url = user.get('showcase_landscape', 'https://picsum.photos/id/102/700/250')  # 横向 1980*1080
        showcase_other_url = user.get('showcase_other', 'https://picsum.photos/id/103/400/400')  # 方形 1000*1000
        
        # 生成图片（带缓存）
        img = generate_profile_image(
            vertical_img_url=vertical_img_url,
            avatar_url=avatar_url,
            horizontal_img_url=horizontal_img_url,
            showcase_other_url=showcase_other_url,
            profile_data=profile_data,
            title_text="CYX-bot 兽频道档案"
        )
        
        # 构建文本内容（使用格式化函数）
        text = f" 用户档案：{username}\n\n"
        text += format_user_info(user)
        
        if img:
            # 将图片转换为字节流发送
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            await send_image_with_text(user_profile_cmd, image_bytes=img_bytes, text=text)
        else:
            await user_profile_cmd.finish(text)
            
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await user_profile_cmd.finish(f"没有该数据（{username}），请尝试输入全名或 ID")
    except Exception as e:
        await user_profile_cmd.finish(f"获取失败：{str(e)}")


# 用户角色命令
user_characters_cmd = on_command("崽崽", aliases={"角色列表"}, priority=5, block=True)


@user_characters_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    username = arg.extract_plain_text().strip()
    if not username:
        await user_characters_cmd.finish("请提供用户名，例如：.用户角色 example")
    
    try:
        data = await furtv_api.get_user_characters(username)
        
        # 支持多种返回结构
        characters = None
        if 'characters' in data:
            characters = data.get('characters', [])
        elif 'data' in data:
            characters = data.get('data', [])
        
        if not characters:
            await user_characters_cmd.finish(f"用户 '{username}' 暂无角色")
        
        # 构建消息列表
        items = []
        for char in characters:
            name = char.get('name', '未知')
            species = char.get('species', '未知')
            worldview = char.get('worldview', '')
            avatar_url = char.get('images', [None])[0] if char.get('images') else None
            
            # 构建文本
            text = f"{name}\n"
            text += f"物种：{species}\n"
            
            # 添加世界观（截断）
            if worldview:
                if len(worldview) > 50:
                    worldview = worldview[:47] + '...'
                text += f"设定：{worldview}\n"
            
            items.append({
                'image_url': avatar_url,
                'text': text
            })
        
        # 使用合并转发或单条消息
        await send_forward_message(user_characters_cmd, event, items, f"{username}的角色")
        return await user_characters_cmd.finish()
        
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await user_characters_cmd.finish(f"没有该数据（{username}），请尝试输入全名或 ID")
    except Exception as e:
        await user_characters_cmd.finish(f"获取失败：{str(e)}")


# 聚会统计命令
gatherings_stats_cmd = on_command("聚会统计", priority=5, block=True)


@gatherings_stats_cmd.handle()
async def _(event: MessageEvent):
    try:
        data = await furtv_api.get_gatherings_yearly_stats()
        
        # 支持多种返回结构
        stats = None
        if 'data' in data:
            stats = data.get('data', {})
        elif 'total' in data:
            # 直接返回 total 的情况
            stats = {'total': data.get('total', 0)}
        
        if not stats:
            await gatherings_stats_cmd.finish("获取聚会统计失败")
        
        result = "聚会年度统计\n\n"
        result += f"今年聚会总数：{stats.get('total', 0)}\n"
        result += f"参与人数：{stats.get('participants', 0)}\n"
        
        await gatherings_stats_cmd.finish(result)
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await gatherings_stats_cmd.finish(f"没有该数据")
    except Exception as e:
        await gatherings_stats_cmd.finish(f"获取失败：{str(e)}")


# 本月聚会命令
monthly_gatherings_cmd = on_command("本月聚会", priority=5, block=True)


@monthly_gatherings_cmd.handle()
async def _(event: MessageEvent):
    from datetime import datetime
    now = datetime.now()
    year = now.year
    month = now.month
    
    try:
        data = await furtv_api.get_gatherings_monthly(year, month)
        
        # 支持多种返回结构
        gatherings = None
        if 'gatherings' in data:
            gatherings = data.get('gatherings', [])
        elif 'data' in data:
            data_content = data.get('data')
            # 确保 data 是列表而不是字典
            if isinstance(data_content, list):
                gatherings = data_content
            elif isinstance(data_content, dict) and 'gatherings' in data_content:
                # data 是字典，包含 gatherings 字段
                gatherings = data_content.get('gatherings', [])
            else:
                gatherings = []
        
        if not gatherings:
            await monthly_gatherings_cmd.finish(f"{year}年{month}月暂无聚会")
        
        result = f"{year}年{month}月聚会列表\n\n"
        for i, gathering in enumerate(gatherings[:10], 1):
            title = gathering.get('title', '未知')
            day = gathering.get('day', '未知日期')
            location = gathering.get('locationPublic', gathering.get('location', '未知地点'))
            description = gathering.get('description', '')
            
            # 截断过长的描述
            if description and len(description) > 50:
                description = description[:47] + '...'
            
            result += f"{i}. {title}\n"
            result += f"   日期：{month}月{day}日\n"
            result += f"   地点：{location}\n"
            if description:
                result += f"   简介：{description}\n"
            result += "\n"
        
        await monthly_gatherings_cmd.finish(result)
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await monthly_gatherings_cmd.finish(f"没有该数据")
    except Exception as e:
        await monthly_gatherings_cmd.finish(f"获取失败：{str(e)}")





# 聚会详情命令
gathering_detail_cmd = on_command("聚会详情", priority=5, block=True)


@gathering_detail_cmd.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    gathering_id = arg.extract_plain_text().strip()
    if not gathering_id:
        await gathering_detail_cmd.finish("请提供聚会 ID，例如：.聚会详情 12345")
    
    try:
        data = await furtv_api.get_gathering_detail(gathering_id)
        
        # 支持多种返回结构
        gathering = None
        if 'gathering' in data:
            gathering = data.get('gathering', {})
        elif 'data' in data:
            gathering = data.get('data', {})
        
        if not gathering:
            await gathering_detail_cmd.finish(f"未找到聚会 ID '{gathering_id}'")
        
        result = f"聚会详情\n\n"
        result += f"名称：{gathering.get('title', '未知')}\n"
        
        # 日期处理
        event_date = gathering.get('event_date', gathering.get('day', '未知'))
        if event_date != '未知' and 'T' in str(event_date):
            event_date = event_date.split('T')[0]
        result += f"日期：{event_date}\n"
        
        result += f"地点：{gathering.get('locationPublic', gathering.get('location_city', gathering.get('location', '未知')))}\n"
        result += f"类型：{gathering.get('type_display', gathering.get('type', '未知'))}\n"
        result += f"状态：{gathering.get('status', '未知')}\n"
        description = gathering.get('description', '无')
        if description and len(description) > 100:
            description = description[:97] + '...'
        result += f"描述：{description}\n"
        result += f"参与人数：{gathering.get('current_participants', gathering.get('participants', '0'))}\n"
        

        
        await gathering_detail_cmd.finish(result)
    except FinishedException:
        pass
    except FileNotFoundError as e:
        await gathering_detail_cmd.finish(f"没有该数据（{gathering_id}），请尝试输入全名或 ID")
    except Exception as e:
        await gathering_detail_cmd.finish(f"获取失败：{str(e)}")

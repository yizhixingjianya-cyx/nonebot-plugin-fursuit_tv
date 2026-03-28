from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
from io import BytesIO
from typing import Dict, Optional
import logging
import os
import hashlib
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# 当前文件路径
current_file_path = os.path.abspath(__file__)
# ftv 插件文件夹路径
ftv_dir = os.path.dirname(current_file_path)
# 项目根目录路径（src/plugins 的上级目录）
project_root = os.path.dirname(os.path.dirname(ftv_dir))

# 使用插件相对目录的字体路径
ziti = os.path.join(ftv_dir, "fonts") + "/"

# 图片缓存目录
image_cache_dir = Path(ftv_dir) / "cache" / "images"
image_cache_dir.mkdir(parents=True, exist_ok=True)

# 缓存过期时间（1 小时）
CACHE_EXPIRY = 3600  # 秒


def _get_cache_key(prefix: str, urls: list) -> str:
    """生成缓存文件的唯一键"""
    url_str = "|".join(urls)
    hash_key = hashlib.md5(url_str.encode()).hexdigest()
    return f"{prefix}_{hash_key}"


def _load_cached_image(cache_key: str) -> Optional[Image.Image]:
    """从缓存加载图片"""
    cache_file = image_cache_dir / f"{cache_key}.png"
    
    if cache_file.exists():
        # 检查缓存是否过期（通过文件修改时间）
        file_mtime = cache_file.stat().st_mtime
        if time.time() - file_mtime < CACHE_EXPIRY:
            try:
                logger.debug(f"使用缓存图片：{cache_file.name}")
                return Image.open(cache_file)
            except Exception as e:
                logger.warning(f"读取缓存图片失败：{e}")
                cache_file.unlink(missing_ok=True)
        else:
            logger.debug(f"缓存图片已过期：{cache_file.name}")
            cache_file.unlink(missing_ok=True)
    
    return None


def _save_to_cache(img: Image.Image, cache_key: str):
    """保存图片到缓存"""
    cache_file = image_cache_dir / f"{cache_key}.png"
    try:
        img.save(cache_file, format='PNG')
        logger.debug(f"已保存缓存图片：{cache_file.name}")
    except Exception as e:
        logger.warning(f"保存缓存图片失败：{e}")


def generate_profile_image(
    vertical_img_url: str,
    avatar_url: str,
    horizontal_img_url: str,
    showcase_other_url: str,
    profile_data: Dict,
    title_text: str = "CYX-bot 兽频道档案",
    max_intro_length: int = 20,  # 简介最大长度限制
    max_intro_lines: int = 3     # 简介最大行数限制
) -> Optional[Image.Image]:
    try:
        # 生成缓存键
        cache_key = _get_cache_key(
            "profile",
            [vertical_img_url, avatar_url, horizontal_img_url, showcase_other_url, str(profile_data.get('id', ''))]
        )
        
        # 尝试从缓存加载
        cached_img = _load_cached_image(cache_key)
        if cached_img:
            logger.info(f"使用缓存的档案图片 | 用户：{profile_data.get('nickname', 'unknown')}")
            return cached_img
        
        logger.info(f"开始生成档案图片，使用的 URLs: "
                   f"vertical={vertical_img_url[:50]}..., "
                   f"avatar={avatar_url[:50]}..., "
                   f"horizontal={horizontal_img_url[:50]}..., "
                   f"showcase={showcase_other_url[:50]}...")
        
        # 1. 处理竖版背景图（1000x1500）
        img_v = _load_valid_image(
            img_url=vertical_img_url,
            default_url="https://picsum.photos/id/100/800/1600",
            img_type="竖版背景图",
            profile_id=profile_data.get("id", "unknown")
        )
        if not img_v:
            logger.error(f"档案{profile_data.get('id')}无法加载竖版背景图，终止图片生成")
            return None
        
        blurred_img = img_v.filter(ImageFilter.GaussianBlur(radius=10))
        background = blurred_img.resize((1000, 1500), Image.Resampling.LANCZOS)

        # 2. 绘制圆角矩形（70% 透明度，范围：100-900x100-1400）
        rect_left, rect_top = 100, 100
        rect_right, rect_bottom = 900, 1400  # 矩形宽 800，高 1300
        corner_radius = 20
        rect_fill = (255, 255, 255, 127)  # 70% 透明度

        draw = ImageDraw.Draw(background)
        draw.rounded_rectangle(
            [(rect_left, rect_top), (rect_right, rect_bottom)],
            radius=corner_radius,
            outline="white",
            width=5,
            fill=rect_fill
        )

        # 3. 加载字体（定义层级）
        try:
            title_font = ImageFont.truetype(f"{ziti}Cubic_11.ttf", 40)
            nickname_font = ImageFont.truetype(f"{ziti}Cubic_11.ttf", 30)
            content_font = ImageFont.truetype(f"{ziti}Cubic_11.ttf", 20)
            footer_font = ImageFont.truetype(f"{ziti}Cubic_11.ttf", 18)
            logger.debug("成功加载 Cubic_11 字体")
        except Exception as e:
            logger.warning(f"加载 Cubic_11 字体失败：{str(e)}，尝试加载 hanyi 字体")
            try:
                title_font = ImageFont.truetype(f"{ziti}hanyi.otf", 40)
                nickname_font = ImageFont.truetype(f"{ziti}hanyi.otf", 30)
                content_font = ImageFont.truetype(f"{ziti}mi.ttf", 20)
                footer_font = ImageFont.truetype(f"{ziti}hanyi.otf", 18)
                logger.debug("成功加载 hanyi 字体")
            except Exception as e:
                logger.warning(f"加载 hanyi 字体失败：{str(e)}，使用默认字体")
                title_font = ImageFont.load_default()
                nickname_font = ImageFont.load_default()
                content_font = ImageFont.load_default()
                footer_font = ImageFont.load_default()

        # 4. 顶部标题（居中）
        title_y = rect_top + 30  # 距矩形顶部 30px
        title_x = (rect_left + rect_right) // 2  # 水平居中
        title_width = draw.textlength(title_text, font=title_font)
        draw.text(
            (title_x - title_width//2, title_y),
            title_text,
            font=title_font,
            fill="#222222"
        )

        # 5. 处理头像（200x200）+ 下方放大昵称
        img_a = _load_valid_image(
            img_url=avatar_url,
            default_url="https://picsum.photos/id/101/200/200",
            img_type="头像",
            profile_id=profile_data.get("id", "unknown")
        )
        if not img_a:
            logger.error(f"档案{profile_data.get('id')}无法加载头像，终止图片生成")
            return None
        
        img_a_resized = img_a.resize((200, 200), Image.Resampling.LANCZOS)
        # 头像位置：左对齐，距矩形顶部 150px（避开标题）
        img_a_x = rect_left + 50  # 距左边缘 50px
        img_a_y = rect_top + 150  # 距顶部 150px（标题占约 60px+ 间距 40px）
        background.paste(
            img_a_resized,
            (img_a_x, img_a_y),
            img_a_resized.convert("RGBA").split()[-1] if img_a.mode == "RGBA" else None
        )

        # 头像下方的放大昵称（居中对齐头像）
        nickname = profile_data.get("nickname", "未知昵称")
        nickname_y = img_a_y + 200 + 15  # 头像底部 +15px 间距
        nickname_x = img_a_x + 100  # 头像中点 x 坐标（200/2=100）
        nickname_width = draw.textlength(nickname, font=nickname_font)
        draw.text(
            (nickname_x - nickname_width//2, nickname_y),  # 相对于头像居中
            nickname,
            font=nickname_font,
            fill="#222222"  # 深色突出昵称
        )

        # 6. 右侧文字信息（用户 ID、兽种等）
        # 文字起始位置：头像右侧 50px，与头像顶部平齐
        text_x = img_a_x + 200 + 50  # 头像右侧 50px
        text_y = img_a_y  # 与头像顶部对齐（y 坐标相同）

        # 用户名
        username = profile_data.get("username", "unknown_username")
        draw.text((text_x, text_y), f"用户名：{username}", font=content_font, fill="#333333")
        text_y += 30
        
        # 用户 ID
        user_id = profile_data.get("id", "未知 ID")
        draw.text((text_x, text_y), f"用户 ID: {user_id}", font=content_font, fill="#333333")
        text_y += 30

        # 兽种
        species = profile_data.get("fursuit_species", "未填写")
        draw.text((text_x, text_y), f"兽种：{species}", font=content_font, fill="#333333")
        text_y += 30

        # 兽装生日
        birthday = profile_data.get("fursuit_birthday", "无")
        draw.text((text_x, text_y), f"兽装生日：{birthday[:10]}", font=content_font, fill="#333333")
        text_y += 30
        
        # 制作师/工作室
        maker = profile_data.get("fursuit_maker", "未知")
        draw.text((text_x, text_y), f"制作师：{maker}", font=content_font, fill="#333333")
        text_y += 30
        
        # 位置信息
        location = profile_data.get("location", "未知")
        draw.text((text_x, text_y), f"位置：{location}", font=content_font, fill="#333333")
        text_y += 20

        # 个人简介（自动换行并限制长度和行数）
        intro = profile_data.get("introduction", "无")
        intro_str = str(intro) if intro is not None else "无"
        
        # 限制简介最大长度
        if len(intro_str) > max_intro_length:
            intro_str = intro_str[:max_intro_length] + "..."
            logger.debug(f"档案{profile_data.get('id')}的简介过长，已截断至{max_intro_length}字符")
        
        draw.text((text_x, text_y), "个人简介:", font=content_font, fill="#333333")
        text_y += 25
        
        # 绘制带行数限制的简介文本
        text_y = _draw_wrapped_text(
            draw, 
            intro_str, 
            text_x, 
            text_y, 
            content_font, 
            max_width=500, 
            line_spacing=5,
            max_lines=max_intro_lines  # 限制最大行数
        )
        text_y += 30

        # 兴趣爱好
        interests = profile_data.get("interests", [])
        if isinstance(interests, list):
            interests_str = ", ".join([str(item) for item in interests]) if interests else "无"
        else:
            interests_str = str(interests) if interests else "无"
        draw.text((text_x, text_y), "兴趣爱好:", font=content_font, fill="#333333")
        text_y += 25
        text_y = _draw_wrapped_text(draw, interests_str, text_x, text_y, content_font, max_width=500, line_spacing=5)
        text_y += 40  # 与下方图片留间距

        # 7. showcase_other 图片（1:1 比例，裁剪为 400x400）
        img_showcase = _load_valid_image(
            img_url=showcase_other_url,
            default_url="https://picsum.photos/id/103/400/400",
            img_type="showcase_other 图片",
            profile_id=profile_data.get("id", "unknown")
        )
        if not img_showcase:
            logger.warning(f"档案{profile_data.get('id')}的 showcase_other 图片加载失败，使用占位空间")
            # 绘制灰色占位框（400x400）
            showcase_x = rect_left + 100
            showcase_y = text_y
            draw.rectangle(
                [(showcase_x, showcase_y), (showcase_x + 400, showcase_y + 400)],
                fill=(240, 240, 240),
                outline="#cccccc",
                width=2
            )
            text_y += 400 + 20
        else:
            # 裁剪为 1:1 比例（取中心区域）
            img_width, img_height = img_showcase.size
            min_dim = min(img_width, img_height)
            left = (img_width - min_dim) // 2
            top = (img_height - min_dim) // 2
            right = left + min_dim
            bottom = top + min_dim
            img_showcase_cropped = img_showcase.crop((left, top, right, bottom))
            img_showcase_resized = img_showcase_cropped.resize((400, 400), Image.Resampling.LANCZOS)
            showcase_x = (rect_left + rect_right) // 2 - 200
            showcase_y = text_y
            background.paste(
                img_showcase_resized,
                (showcase_x, showcase_y),
                img_showcase_resized.convert("RGBA").split()[-1] if img_showcase.mode == "RGBA" else None
            )
            text_y = showcase_y + 400 + 20

        # 8. 横版展示图（700x250）
        img_h = _load_valid_image(
            img_url=horizontal_img_url,
            default_url="https://picsum.photos/id/102/700/250",
            img_type="横版展示图",
            profile_id=profile_data.get("id", "unknown")
        )
        if not img_h:
            logger.error(f"档案{profile_data.get('id')}无法加载横版展示图，终止图片生成")
            return None
        
        img_h_resized = img_h.resize((570, 300), Image.Resampling.LANCZOS)
        img_h_x = rect_left + 100
        img_h_y = rect_bottom - 150 - 250
        background.paste(
            img_h_resized,
            (img_h_x, img_h_y),
            img_h_resized.convert("RGBA").split()[-1] if img_h.mode == "RGBA" else None
        )

        # 9. 底部尾部文字
        footer_text = "兽频道 API from VDS"
        footer_y = img_h_y + 300 + 20
        footer_width = draw.textlength(footer_text, font=footer_font)
        footer_x = (rect_left + rect_right) // 2 - footer_width//2
        draw.text(
            (footer_x, footer_y),
            footer_text,
            font=footer_font,
            fill="#666666"
        )

        logger.info(f"档案{profile_data.get('id')}图片生成成功")
        
        # 保存到缓存
        _save_to_cache(background, cache_key)
        
        return background

    except Exception as e:
        logger.error(f"档案{profile_data.get('id')}图片生成失败：{str(e)}", exc_info=True)
        return None


def _download_and_cache_image(url: str, img_type: str = "图片") -> Optional[BytesIO]:
    """下载并缓存图片
    
    Args:
        url: 图片 URL
        img_type: 图片类型描述
    
    Returns:
        BytesIO 对象，失败返回 None
    """
    try:
        # 生成缓存文件名（使用 URL 的 MD5）
        filename = hashlib.md5(url.encode()).hexdigest() + '.jpg'
        cache_path = image_cache_dir / filename
        
        # 检查缓存
        if cache_path.exists():
            logger.debug(f"✅ 使用缓存{img_type} | {filename}")
            with open(cache_path, 'rb') as f:
                return BytesIO(f.read())
        
        # 下载图片
        logger.debug(f"下载{img_type} | {url[:50]}...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        # 保存到缓存
        with open(cache_path, 'wb') as f:
            f.write(response.content)
        
        logger.debug(f"💾 已缓存{img_type} | {filename} | 大小：{len(response.content)} 字节")
        return BytesIO(response.content)
    
    except Exception as e:
        logger.error(f"下载{img_type}失败：{e}")
        return None


def _load_valid_image(
    img_url: str,
    default_url: str,
    img_type: str,
    profile_id: str
) -> Optional[Image.Image]:
    """加载并验证图片，使用缓存机制"""
    # 尝试从缓存加载
    cached_data = _download_and_cache_image(img_url, img_type)
    
    if cached_data:
        try:
            img = Image.open(cached_data)
            img.load()  # 强制加载图片数据
            return img
        except Exception as e:
            logger.warning(f"{img_type}缓存文件损坏，尝试默认图片：{e}")
    
    # 缓存失败时使用默认图片
    logger.warning(f"{img_type}加载失败（档案 ID: {profile_id}），使用默认图片")
    default_data = _download_and_cache_image(default_url, f"默认{img_type}")
    
    if default_data:
        try:
            img = Image.open(default_data)
            img.load()
            return img
        except Exception as e:
            logger.error(f"默认{img_type}也加载失败：{e}")
    
    return None


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw, 
    text: str, 
    x: int, 
    y: int, 
    font: ImageFont.FreeTypeFont, 
    max_width: int, 
    line_spacing: int,
    max_lines: Optional[int] = None  # 新增：最大行数限制，None 表示无限制
) -> int:
    """自动换行绘制文本，支持最大行数限制"""
    words = text.split()
    current_line = ""
    current_y = y
    line_count = 0

    for word in words:
        # 检查是否已达到最大行数
        if max_lines is not None and line_count >= max_lines:
            # 在最后一行添加省略号
            if current_line:
                if draw.textlength(f"{current_line}...", font=font) <= max_width:
                    current_line += "..."
                else:
                    current_line = current_line[:-3] + "..."
                draw.text((x, current_y), current_line, font=font, fill="#333333")
                current_y += font.size + line_spacing
            logger.debug(f"文本已达到最大行数限制 ({max_lines}行)，已截断")
            return current_y

        test_line = f"{current_line} {word}".strip()
        if draw.textlength(test_line, font=font) <= max_width:
            current_line = test_line
        else:
            # 绘制当前行
            draw.text((x, current_y), current_line, font=font, fill="#333333")
            current_y += font.size + line_spacing
            current_line = word
            line_count += 1

    # 绘制最后一行
    if current_line and (max_lines is None or line_count < max_lines):
        draw.text((x, current_y), current_line, font=font, fill="#333333")
        current_y += font.size + line_spacing
        line_count += 1

    return current_y

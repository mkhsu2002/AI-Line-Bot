import os
import json
import logging
import datetime
from openai import OpenAI
from routes.utils.config_service import ConfigManager, get_openai_api_key, get_llm_settings
import models
from app import db

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with OpenAI LLM"""
    
    @staticmethod
    def get_client():
        """Get an OpenAI client instance with the current API key"""
        api_key = get_openai_api_key()
        if not api_key:
            logger.error("OpenAI API key not configured")
            return None
        
        return OpenAI(api_key=api_key)
    
    @staticmethod
    def get_bot_style(style_name=None):
        """Get the bot style prompt by name or use the active style"""
        if not style_name:
            style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "貼心")
        
        style = models.BotStyle.query.filter_by(name=style_name).first()
        if not style:
            # Fallback to default style
            style = models.BotStyle.query.filter_by(name="貼心").first()
            
            # If no default style exists, create it
            if not style:
                style = models.BotStyle(
                    name="貼心",
                    prompt="你是小艾，艾可公司的首位AI智能小編，熱情活潑，充滿正能量，總是用繁體中文交談，給人鼓勵與關懷。",
                    is_default=True
                )
                db.session.add(style)
                db.session.commit()
        
        return style
    
    @staticmethod
    def generate_response(user_message, style_name=None, rag_context=None):
        """Generate a response using the OpenAI API with the specified style"""
        client = LLMService.get_client()
        if not client:
            return "抱歉，無法連接 AI 服務，請檢查 API 設定。"
        
        # Get the bot style
        style = LLMService.get_bot_style(style_name)
        
        # Get OpenAI settings
        settings = get_llm_settings()
        
        # Get current date information
        current_date = datetime.datetime.now()
        date_info = {
            "year": current_date.year,
            "month": current_date.month,
            "day": current_date.day,
            "weekday": current_date.strftime("%A"),
            "hour": current_date.hour,
            "minute": current_date.minute,
            "second": current_date.second,
            "iso_date": current_date.strftime("%Y-%m-%d"),
            "full_date": current_date.strftime("%Y年%m月%d日"),
            "full_time": current_date.strftime("%H:%M:%S"),
            "full_datetime": current_date.strftime("%Y年%m月%d日 %H:%M:%S")
        }
        
        date_prompt = f"""
今天是 {date_info['full_date']}，星期{['一', '二', '三', '四', '五', '六', '日'][current_date.weekday()]}。
當前時間是 {date_info['full_time']}。
如果用戶詢問當前日期或時間，請使用以上信息回答。
"""
        
        # Build the messages
        messages = [
            {"role": "system", "content": style.prompt},
            {"role": "system", "content": date_prompt}
        ]
        
        # Add RAG context if available
        if rag_context:
            messages.append({
                "role": "system", 
                "content": f"Here is some additional context that might be helpful: {rag_context}"
            })
        
        # Add user message
        messages.append({"role": "user", "content": user_message})
        
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=settings["temperature"],
                max_tokens=settings["max_tokens"]
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"抱歉，生成回應時發生錯誤：{str(e)}"
    
    @staticmethod
    def validate_api_key(api_key):
        """Validate that the provided OpenAI API key works"""
        try:
            client = OpenAI(api_key=api_key)
            # Make a small request to validate the key
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5
            )
            return True, "API key is valid"
        except Exception as e:
            logger.error(f"API key validation error: {e}")
            return False, f"API key validation failed: {str(e)}"

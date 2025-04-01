import json
import logging
from flask import Blueprint, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)
from app import db
from models import ChatMessage, LineUser
from config import get_line_config
from llm_service import LLMService
from rag_service import RAGService

webhook_bp = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)

# Initialize the LINE Bot API and handler
def get_line_bot_api():
    """Get a LINE Bot API instance with current config"""
    config = get_line_config()
    return LineBotApi(config['channel_access_token'])

def get_line_webhook_handler():
    """Get a LINE Webhook handler with current config"""
    config = get_line_config()
    return WebhookHandler(config['channel_secret'])

# LINE Bot webhook route
@webhook_bp.route('/webhook', methods=['POST'])
def line_webhook():
    """Handle LINE webhook events"""
    # Get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    
    # Get request body as text
    body = request.get_data(as_text=True)
    
    # Log the request
    logger.info("Request body: %s", body)
    
    # Initialize the webhook handler
    handler = get_line_webhook_handler()
    
    try:
        # Handle the webhook
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Check your channel secret.")
        abort(400)
    
    return 'OK'

# Define the event handler for text messages
@get_line_webhook_handler().add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    """Handle text messages from LINE users"""
    # Get message content
    user_id = event.source.user_id
    user_message = event.message.text
    
    # Get or create the LINE user
    line_user = LineUser.query.filter_by(line_user_id=user_id).first()
    if not line_user:
        # Initialize LINE Bot API
        line_bot_api = get_line_bot_api()
        
        try:
            # Get user profile from LINE
            profile = line_bot_api.get_profile(user_id)
            line_user = LineUser(
                line_user_id=user_id,
                display_name=profile.display_name,
                picture_url=profile.picture_url,
                status_message=profile.status_message
            )
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            # Create a minimal user record
            line_user = LineUser(line_user_id=user_id)
        
        db.session.add(line_user)
        db.session.commit()
    
    # Save user message to database
    chat_message = ChatMessage(
        line_user_id=user_id,
        is_user_message=True,
        message_text=user_message
    )
    db.session.add(chat_message)
    db.session.commit()
    
    # Check for style command
    bot_style = None
    if user_message.startswith('/style '):
        style_name = user_message[7:].strip()
        # Set user's preferred style
        line_user.active_style = style_name
        db.session.commit()
        
        response_text = f"風格設定為: {style_name}"
        
        # Save bot response to database
        bot_message = ChatMessage(
            line_user_id=user_id,
            is_user_message=False,
            message_text=response_text,
            bot_style=style_name
        )
        db.session.add(bot_message)
        db.session.commit()
        
        # Send response
        line_bot_api = get_line_bot_api()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=response_text)
        )
        return
    
    # Get RAG context if enabled
    rag_context = RAGService.get_context_for_query(user_message)
    
    # Use the user's preferred style if set
    if line_user.active_style:
        bot_style = line_user.active_style
    
    # Generate response using OpenAI
    response_text = LLMService.generate_response(user_message, bot_style, rag_context)
    
    # Save bot response to database
    bot_message = ChatMessage(
        line_user_id=user_id,
        is_user_message=False,
        message_text=response_text,
        bot_style=bot_style
    )
    db.session.add(bot_message)
    db.session.commit()
    
    # Send response
    line_bot_api = get_line_bot_api()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response_text)
    )

# Webhook verification endpoint
@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """Verify the webhook URL for LINE Platform"""
    return 'Webhook OK'

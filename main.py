import os
import logging
from flask import Flask, request, abort, render_template, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
from linebot import LineBotApi
import json
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase
from services.llm_service import LLMService
# Import blueprints for route organization
from routes.webhook import webhook_bp

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize Flask extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "flypig-line-bot-secret")

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///flypig.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with app
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BotStyle(db.Model):
    """Model to store different bot response styles"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    
class ChatMessage(db.Model):
    """Model to store chat message history"""
    id = db.Column(db.Integer, primary_key=True)
    line_user_id = db.Column(db.String(64), nullable=False)
    is_user_message = db.Column(db.Boolean, default=True)
    message_text = db.Column(db.Text, nullable=False)
    bot_style = db.Column(db.String(64), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Config(db.Model):
    """Model to store configuration values"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

# Setup login manager
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Configuration manager
class ConfigManager:
    """Configuration manager for the application"""
    
    @staticmethod
    def get(key, default=None):
        """Get a configuration value from the database"""
        config = Config.query.filter_by(key=key).first()
        if config:
            return config.value
        return default
    
    @staticmethod
    def set(key, value):
        """Set a configuration value in the database"""
        config = Config.query.filter_by(key=key).first()
        if config:
            config.value = value
        else:
            config = Config(key=key, value=value)
            db.session.add(config)
        db.session.commit()

# LLM service
def get_openai_api_key():
    """Get OpenAI API key from environment or database"""
    # First check environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return api_key
    
    # Then check database
    return ConfigManager.get("OPENAI_API_KEY")

def get_line_config():
    """Get LINE configuration from database"""
    channel_id = ConfigManager.get("LINE_CHANNEL_ID", "")
    channel_secret = ConfigManager.get("LINE_CHANNEL_SECRET", "")
    channel_access_token = ConfigManager.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    
    return {
        "channel_id": channel_id,
        "channel_secret": channel_secret,
        "channel_access_token": channel_access_token
    }

def get_llm_settings():
    """Get LLM settings from database"""
    temperature = float(ConfigManager.get("OPENAI_TEMPERATURE", "0.7"))
    max_tokens = int(ConfigManager.get("OPENAI_MAX_TOKENS", "500"))
    
    return {
        "temperature": temperature,
        "max_tokens": max_tokens
    }

def get_bot_style(style_name=None):
    """Get the bot style prompt by name or use the active style"""
    if not style_name:
        style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "Default")
    
    style = BotStyle.query.filter_by(name=style_name).first()
    if not style:
        # Fallback to default style
        style = BotStyle.query.filter_by(name="Default").first()
        
        # If no default style exists, create it
        if not style:
            style = BotStyle(
                name="Default",
                prompt="You are a helpful assistant. Respond in a straightforward manner.",
                is_default=True
            )
            db.session.add(style)
            db.session.commit()
    
    return style

def generate_response(user_message, style_name=None):
    """Generate a response using the OpenAI API with the specified style"""
    api_key = get_openai_api_key()
    if not api_key:
        return "API key not configured, please set up OpenAI API key."
    
    client = OpenAI(api_key=api_key)
    
    # Get the bot style
    style = get_bot_style(style_name)
    
    # Get OpenAI settings
    settings = get_llm_settings()
    
    # Build the messages
    messages = [
        {"role": "system", "content": style.prompt},
        {"role": "user", "content": user_message}
    ]
    
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
        return f"Error generating response: {str(e)}"

# LINE Bot service
def get_line_bot_api():
    """Get a LINE Bot API instance with current config"""
    config = get_line_config()
    return LineBotApi(config["channel_access_token"])

def get_line_webhook_handler():
    """Get a LINE Webhook handler with current config"""
    return get_webhook_handler()

# Create tables and initial data
with app.app_context():
    db.create_all()
    
    # Create initial admin user if no users exist
    if not User.query.first():
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash=generate_password_hash("admin"),
            is_admin=True
        )
        db.session.add(admin)
        
        # Create default bot styles
        default_styles = [
            BotStyle(name="貼心", prompt="你是阿昌，和宸清潔庇護工場的代言人，一生奉獻給公益，關懷弱勢，充滿理想與正能量，只用繁體中文聊天，專注陪伴聊天，不碰程式碼或畫圖。", is_default=True),
            BotStyle(name="風趣", prompt="你是一位風趣幽默的阿昌，擅長用輕鬆詼諧的語調回答問題，回應中帶有俏皮的繁體中文表達方式，但不失專業與幫助性。"),
            BotStyle(name="認真", prompt="你是阿昌，一位非常專業的助理，使用正式、商務化的繁體中文進行溝通，提供精確的資訊和適當的建議。"),
            BotStyle(name="專業", prompt="你是阿昌，一位技術專家助理，提供詳細、專業的繁體中文回應，使用特定的技術術語和全面的解釋，讓用戶對技術問題有更深入的理解。"),
        ]
        for style in default_styles:
            db.session.add(style)
        
        # Create default config values
        default_configs = [
            Config(key="OPENAI_TEMPERATURE", value="0.7"),
            Config(key="OPENAI_MAX_TOKENS", value="500"),
            Config(key="LINE_CHANNEL_ID", value=""),
            Config(key="LINE_CHANNEL_SECRET", value=""),
            Config(key="LINE_CHANNEL_ACCESS_TOKEN", value=""),
            Config(key="ACTIVE_BOT_STYLE", value="貼心"),
        ]
        for config in default_configs:
            db.session.add(config)
        
        db.session.commit()
        logger.info("Created initial admin user and default settings")

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        
        flash('使用者名稱或密碼錯誤', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get message statistics
    total_messages = ChatMessage.query.count()
    user_messages = ChatMessage.query.filter_by(is_user_message=True).count()
    bot_messages = ChatMessage.query.filter_by(is_user_message=False).count()
    
    # Get recent messages
    recent_messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).limit(10).all()
    
    return render_template('dashboard.html', 
                           total_messages=total_messages,
                           user_messages=user_messages, 
                           bot_messages=bot_messages,
                           recent_messages=recent_messages)

@app.route('/bot-settings', methods=['GET', 'POST'])
@login_required
def bot_settings():
    if request.method == 'POST':
        channel_id = request.form.get('channel_id')
        channel_secret = request.form.get('channel_secret')
        channel_access_token = request.form.get('channel_access_token')
        active_style = request.form.get('active_style')
        
        ConfigManager.set("LINE_CHANNEL_ID", channel_id)
        ConfigManager.set("LINE_CHANNEL_SECRET", channel_secret)
        ConfigManager.set("LINE_CHANNEL_ACCESS_TOKEN", channel_access_token)
        ConfigManager.set("ACTIVE_BOT_STYLE", active_style)
        
        flash('機器人設定已成功儲存', 'success')
        return redirect(url_for('bot_settings'))
    
    config = get_line_config()
    active_style = ConfigManager.get("ACTIVE_BOT_STYLE", "貼心")
    styles = BotStyle.query.all()
    
    return render_template('bot_settings.html', 
                           config=config, 
                           active_style=active_style,
                           styles=styles)

@app.route('/llm-settings', methods=['GET', 'POST'])
@login_required
def llm_settings():
    if request.method == 'POST':
        api_key = request.form.get('api_key')
        temperature = request.form.get('temperature')
        max_tokens = request.form.get('max_tokens')
        
        ConfigManager.set("OPENAI_API_KEY", api_key)
        ConfigManager.set("OPENAI_TEMPERATURE", temperature)
        ConfigManager.set("OPENAI_MAX_TOKENS", max_tokens)
        
        flash('LLM 設定已成功儲存', 'success')
        return redirect(url_for('llm_settings'))
    
    settings = get_llm_settings()
    api_key = get_openai_api_key() or ""
    
    return render_template('llm_settings.html', 
                           api_key=api_key,
                           temperature=settings["temperature"],
                           max_tokens=settings["max_tokens"])

@app.route('/bot-styles', methods=['GET'])
@login_required
def bot_styles():
    styles = BotStyle.query.all()
    return render_template('bot_styles.html', styles=styles)

@app.route('/edit-bot-style/<int:style_id>', methods=['GET', 'POST'])
@login_required
def edit_bot_style(style_id):
    # Get the style by ID
    style = BotStyle.query.get_or_404(style_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        prompt = request.form.get('prompt')
        is_default = 'is_default' in request.form
        
        # Check if another style with this name already exists (exclude current style)
        existing_style = BotStyle.query.filter(BotStyle.name == name, BotStyle.id != style_id).first()
        if existing_style:
            flash(f'名稱為 "{name}" 的風格已存在', 'danger')
            return redirect(url_for('edit_bot_style', style_id=style_id))
        
        # Update the style
        style.name = name
        style.prompt = prompt
        style.is_default = is_default
        
        # If this is set as default, update all others
        if is_default:
            for other_style in BotStyle.query.filter(BotStyle.id != style_id).all():
                other_style.is_default = False
            
            # Update active style
            ConfigManager.set("ACTIVE_BOT_STYLE", name)
        
        db.session.commit()
        flash('機器人風格已成功更新', 'success')
        return redirect(url_for('bot_styles'))
    
    return render_template('edit_bot_style.html', style=style)

@app.route('/add-bot-style', methods=['GET', 'POST'])
@login_required
def add_bot_style():
    if request.method == 'POST':
        name = request.form.get('name')
        prompt = request.form.get('prompt')
        is_default = 'is_default' in request.form
        
        # Check if style with this name already exists
        existing_style = BotStyle.query.filter_by(name=name).first()
        if existing_style:
            flash(f'名稱為 "{name}" 的風格已存在', 'danger')
            return redirect(url_for('add_bot_style'))
        
        style = BotStyle(name=name, prompt=prompt, is_default=is_default)
        db.session.add(style)
        
        # If this is set as default, update all others
        if is_default:
            for other_style in BotStyle.query.filter(BotStyle.id != style.id).all():
                other_style.is_default = False
            
            # Update active style
            ConfigManager.set("ACTIVE_BOT_STYLE", name)
        
        db.session.commit()
        flash('機器人風格已成功新增', 'success')
        return redirect(url_for('bot_styles'))
    
    return render_template('add_bot_style.html')

@app.route('/message-history')
@login_required
def message_history():
    messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).all()
    return render_template('message_history.html', messages=messages)

# Webhook routes are now handled by routes/webhook.py using blueprint

# Initialize handler at global level
webhook_handler = None

def get_webhook_handler():
    """Get or create a webhook handler"""
    global webhook_handler
    if webhook_handler is None:
        config = get_line_config()
        webhook_handler = WebhookHandler(config["channel_secret"])
        
        # Register message event handler
        @webhook_handler.add(MessageEvent, message=TextMessage)
        def handle_text_message(event):
            """Handle text messages from LINE users"""
            try:
                # Get message content
                user_id = event.source.user_id
                user_message = event.message.text
                
                # Save user message to database
                chat_message = ChatMessage(
                    line_user_id=user_id,
                    is_user_message=True,
                    message_text=user_message
                )
                db.session.add(chat_message)
                db.session.commit()
                
                # Check for style command
                style_name = None
                if user_message.startswith('/style '):
                    style_name = user_message[7:].strip()
                    style = BotStyle.query.filter_by(name=style_name).first()
                    if style:
                        response_text = f"風格已設定為: {style_name}"
                    else:
                        response_text = f"找不到風格: {style_name}，請使用有效的風格名稱"
                else:
                    # 使用本地函數產生回應，而非LLMService
                    api_key = get_openai_api_key()
                    if not api_key:
                        response_text = "API key 未設定，請在管理後台設定 OpenAI API key。"
                    else:
                        client = OpenAI(api_key=api_key)
                        
                        # 獲取風格
                        default_style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "貼心")
                        style = BotStyle.query.filter_by(name=default_style_name).first()
                        if not style:
                            style = BotStyle.query.filter_by(name="貼心").first()
                        
                        if not style:
                            response_text = "無法找到有效的機器人風格，請在管理後台設定。"
                        else:
                            # 獲取設定
                            settings = get_llm_settings()
                            
                            # 構建訊息
                            messages = [
                                {"role": "system", "content": style.prompt},
                                {"role": "user", "content": user_message}
                            ]
                            
                            # 呼叫API
                            response = client.chat.completions.create(
                                model="gpt-4o",
                                messages=messages,
                                temperature=settings["temperature"],
                                max_tokens=settings["max_tokens"]
                            )
                            
                            response_text = response.choices[0].message.content
                
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
            except Exception as e:
                logger.error(f"Webhook handling error: {e}")
                # 即使發生錯誤，至少嘗試回覆一個錯誤訊息
                try:
                    line_bot_api = get_line_bot_api()
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"很抱歉，處理您的訊息時出現了問題。")
                    )
                except:
                    logger.error("Failed to send error message to LINE user")
    
    return webhook_handler

# Web API endpoint for testing the bot
@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json
        if not data or 'message' not in data:
            return jsonify({'error': 'Invalid request'}), 400
            
        user_message = data['message']
        style_name = data.get('style')
        
        # 使用本地函數而非LLMService
        api_key = get_openai_api_key()
        if not api_key:
            return jsonify({'error': 'API key not configured'}), 500
        
        client = OpenAI(api_key=api_key)
        
        # 獲取機器人風格
        if not style_name:
            style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "貼心")
        
        style = BotStyle.query.filter_by(name=style_name).first()
        if not style:
            style = BotStyle.query.filter_by(name="貼心").first()
            
        if not style:
            return jsonify({'error': '找不到對應的機器人風格'}), 500
            
        # 獲取OpenAI設定
        settings = get_llm_settings()
        
        # 構建訊息
        messages = [
            {"role": "system", "content": style.prompt},
            {"role": "user", "content": user_message}
        ]
        
        # 呼叫API
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=settings["temperature"],
            max_tokens=settings["max_tokens"]
        )
        
        return jsonify({'response': response.choices[0].message.content})
    except Exception as e:
        logger.error(f"API chat error: {e}")
        return jsonify({'error': f"服務錯誤: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

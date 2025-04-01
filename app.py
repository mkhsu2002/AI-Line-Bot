import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager

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
database_url = os.environ.get("DATABASE_URL", "sqlite:///flypig.db")
# Ensure PostgreSQL URL compatibility with SQLAlchemy
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with app
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Import and initialize models
import models

# Setup model classes with SQLAlchemy
models.User = type('User', (models.User, db.Model), {})
models.LineUser = type('LineUser', (models.LineUser, db.Model), {})
models.ChatMessage = type('ChatMessage', (models.ChatMessage, db.Model), {})
models.BotStyle = type('BotStyle', (models.BotStyle, db.Model), {})
models.Config = type('Config', (models.Config, db.Model), {})
models.Document = type('Document', (models.Document, db.Model), {})
models.LogEntry = type('LogEntry', (models.LogEntry, db.Model), {})

# Import for easy access
User = models.User
BotStyle = models.BotStyle
Config = models.Config

# Create tables and initialize data
with app.app_context():
    # Create tables if they don't exist
    db.create_all()
    
    # Create initial admin user if no users exist
    if not User.query.first():
        from werkzeug.security import generate_password_hash
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash=generate_password_hash("admin"),
            is_admin=True
        )
        db.session.add(admin)
        
        # Create default bot styles
        default_styles = [
            BotStyle(name="預設", prompt="你是阿昌，和宸清潔庇護工場的代言人，一生奉獻給公益，關懷弱勢，充滿理想與正能量，只用繁體中文聊天，專注陪伴聊天，不碰程式碼或畫圖。", is_default=True),
            BotStyle(name="風趣", prompt="你是一位風趣幽默的阿昌，擅長用輕鬆詼諧的語調回答問題，回應中帶有俏皮的繁體中文表達方式，但不失專業與幫助性。"),
            BotStyle(name="正式", prompt="你是阿昌，一位非常專業的助理，使用正式、商務化的繁體中文進行溝通，提供精確的資訊和適當的建議。"),
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
            Config(key="ACTIVE_BOT_STYLE", value="預設"),
            Config(key="RAG_ENABLED", value="False"),
        ]
        for config in default_configs:
            db.session.add(config)
        
        db.session.commit()
        logger.info("Created initial admin user and default settings")

# Setup login manager
@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Register blueprints
from routes.admin import admin_bp
from routes.webhook import webhook_bp
from routes.auth import auth_bp

app.register_blueprint(admin_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(auth_bp)

# Create knowledge_base directory if it doesn't exist
import os
if not os.path.exists("knowledge_base"):
    os.makedirs("knowledge_base")
    logger.info("Created knowledge_base directory")

logger.info("Application initialization complete")

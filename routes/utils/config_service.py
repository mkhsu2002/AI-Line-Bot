import os
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    """Configuration manager for the application"""
    
    # Cache for configuration values
    _config_cache = {}
    
    @staticmethod
    def get(key, default=None):
        """Get a configuration value from the database or cache"""
        # Try to get the value from cache first
        if key in ConfigManager._config_cache:
            return ConfigManager._config_cache[key]
        
        # Check environment variables first
        env_value = os.environ.get(key)
        if env_value is not None:
            ConfigManager._config_cache[key] = env_value
            return env_value
        
        # Try to get from database, but only if within flask app context
        try:
            # Import Flask dependencies inside the function to avoid circular imports
            from flask import current_app
            from app import db
            import models
            
            # Only try to query the database if we're inside an application context
            with current_app.app_context():
                # Then check the database
                config_entry = models.Config.query.filter_by(key=key).first()
                if config_entry and config_entry.value:
                    ConfigManager._config_cache[key] = config_entry.value
                    return config_entry.value
        except Exception as e:
            # Either not in app context, or another error occurred
            logger.debug(f"Could not query database for config {key}: {str(e)}")
            # Fall back to default
        
        # Return the default value if nothing found
        return default
    
    @staticmethod
    def set(key, value):
        """Set a configuration value in the database and cache"""
        # Update cache
        ConfigManager._config_cache[key] = value
        
        try:
            # Import Flask dependencies inside the function to avoid circular imports
            from flask import current_app
            from app import db
            import models
            
            # Only try to update the database if we're inside an application context
            with current_app.app_context():
                # Update database
                config_entry = models.Config.query.filter_by(key=key).first()
                if config_entry:
                    config_entry.value = value
                else:
                    new_config = models.Config(key=key, value=value)
                    db.session.add(new_config)
                
                db.session.commit()
        except Exception as e:
            # Either not in app context, or another error occurred
            logger.debug(f"Could not update database for config {key}: {str(e)}")
            # Cache is still updated
    
    @staticmethod
    def get_all():
        """Get all configuration entries from the database"""
        result = {}
        
        try:
            # Import Flask dependencies inside the function to avoid circular imports
            from flask import current_app
            import models
            
            # Only try to query the database if we're inside an application context
            with current_app.app_context():
                configs = models.Config.query.all()
                
                for config in configs:
                    # Check if there's an environment variable that overrides the database value
                    env_value = os.environ.get(config.key)
                    if env_value is not None:
                        result[config.key] = env_value
                    else:
                        result[config.key] = config.value
        except Exception as e:
            # Either not in app context, or another error occurred
            logger.debug(f"Could not query database for all configs: {str(e)}")
            # Return empty result
            
        return result
    
    @staticmethod
    def clear_cache():
        """Clear the configuration cache"""
        ConfigManager._config_cache = {}

# Helper function to get the OpenAI API key with fallback
def get_openai_api_key():
    return ConfigManager.get("OPENAI_API_KEY", "")

# Helper function to get LINE channel configuration
def get_line_config():
    return {
        "channel_id": ConfigManager.get("LINE_CHANNEL_ID", "2007002420"),
        "channel_secret": ConfigManager.get("LINE_CHANNEL_SECRET", "68de5af41837af7d0cf8998774f5dc04"),
        "channel_access_token": ConfigManager.get("LINE_CHANNEL_ACCESS_TOKEN", "VaPdPpIRKyOT8VQHAu3bt/KfCy4pJmLL0O76mv5NTtakPiDrDDEyXLPiNqvldZJlMUnLSJ+sWhNpdXgXpm7SiB4bHVJFbnagaftL6IX3PGz7n/msUBX//L2s/OvuLaNcfTMA1a20CuwIzgoGjiTzMgdB04t89/1O/w1cDnyilFU=")
    }

# Helper function to get the active bot style
def get_active_bot_style():
    return ConfigManager.get("ACTIVE_BOT_STYLE", "貼心")

# Helper function to get LLM settings
def get_llm_settings():
    return {
        "temperature": float(ConfigManager.get("OPENAI_TEMPERATURE", "0.7")),
        "max_tokens": int(ConfigManager.get("OPENAI_MAX_TOKENS", "500"))
    }

# Helper function to check if RAG is enabled
def is_rag_enabled():
    rag_enabled = ConfigManager.get("RAG_ENABLED", "True")
    if rag_enabled is None:
        return True
    return rag_enabled.lower() == "true"
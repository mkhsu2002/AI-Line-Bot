import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import BotStyle, Config, ChatMessage, Document, LineUser, User
from app import db
from forms import LLMSettingsForm, BotStyleForm, BotSettingsForm, DocumentForm, UserForm
from routes.utils.config_service import ConfigManager
from services.llm_service import LLMService
from rag_service import RAGService

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)

# Admin access decorator
def admin_required(f):
    """Decorator to require admin access for a route"""
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required for this page.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return login_required(decorated_function)

# Dashboard
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin dashboard displaying system overview"""
    # Get stats
    user_count = LineUser.query.count()
    message_count = ChatMessage.query.count()
    document_count = Document.query.count()
    
    # Get recent messages
    recent_messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).limit(10).all()
    
    # Get active style
    active_style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "Default")
    active_style = BotStyle.query.filter_by(name=active_style_name).first()
    
    # Get OpenAI API key status
    openai_key = ConfigManager.get("OPENAI_API_KEY", "")
    api_status = "Configured" if openai_key else "Not Configured"
    
    # Get RAG status
    rag_enabled = ConfigManager.get("RAG_ENABLED", "True") == "True"
    
    return render_template(
        'dashboard.html',
        user_count=user_count,
        message_count=message_count,
        document_count=document_count,
        recent_messages=recent_messages,
        active_style=active_style,
        api_status=api_status,
        rag_enabled=rag_enabled
    )

# LLM Settings
@admin_bp.route('/llm_settings', methods=['GET', 'POST'])
@admin_required
def llm_settings():
    """LLM settings configuration page"""
    form = LLMSettingsForm()
    
    # Pre-fill form with current settings
    if request.method == 'GET':
        form.api_key.data = ConfigManager.get("OPENAI_API_KEY", "")
        form.temperature.data = float(ConfigManager.get("OPENAI_TEMPERATURE", "0.7"))
        form.max_tokens.data = int(ConfigManager.get("OPENAI_MAX_TOKENS", "500"))
    
    # Process form submission
    if form.validate_on_submit():
        # Validate API key
        valid, message = LLMService.validate_api_key(form.api_key.data)
        
        if valid:
            # Save settings
            ConfigManager.set("OPENAI_API_KEY", form.api_key.data)
            ConfigManager.set("OPENAI_TEMPERATURE", str(form.temperature.data))
            ConfigManager.set("OPENAI_MAX_TOKENS", str(form.max_tokens.data))
            
            flash('LLM settings updated successfully.', 'success')
            return redirect(url_for('admin.llm_settings'))
        else:
            flash(f'API key validation failed: {message}', 'danger')
    
    return render_template('llm_settings.html', form=form)

# Bot Settings
@admin_bp.route('/bot_settings', methods=['GET', 'POST'])
@admin_required
def bot_settings():
    """LINE Bot settings configuration page"""
    form = BotSettingsForm()
    
    # Get all available styles for the dropdown
    styles = BotStyle.query.all()
    form.active_style.choices = [(style.name, style.name) for style in styles]
    
    # Pre-fill form with current settings
    if request.method == 'GET':
        form.channel_id.data = ConfigManager.get("LINE_CHANNEL_ID", "2007002420")
        form.channel_secret.data = ConfigManager.get("LINE_CHANNEL_SECRET", "68de5af41837af7d0cf8998774f5dc04")
        form.channel_access_token.data = ConfigManager.get("LINE_CHANNEL_ACCESS_TOKEN", "VaPdPpIRKyOT8VQHAu3bt/KfCy4pJmLL0O76mv5NTtakPiDrDDEyXLPiNqvldZJlMUnLSJ+sWhNpdXgXpm7SiB4bHVJFbnagaftL6IX3PGz7n/msUBX//L2s/OvuLaNcfTMA1a20CuwIzgoGjiTzMgdB04t89/1O/w1cDnyilFU=")
        form.active_style.data = ConfigManager.get("ACTIVE_BOT_STYLE", "Default")
        form.rag_enabled.data = ConfigManager.get("RAG_ENABLED", "True") == "True"
    
    # Process form submission
    if form.validate_on_submit():
        # Save settings
        ConfigManager.set("LINE_CHANNEL_ID", form.channel_id.data)
        ConfigManager.set("LINE_CHANNEL_SECRET", form.channel_secret.data)
        ConfigManager.set("LINE_CHANNEL_ACCESS_TOKEN", form.channel_access_token.data)
        ConfigManager.set("ACTIVE_BOT_STYLE", form.active_style.data)
        ConfigManager.set("RAG_ENABLED", str(form.rag_enabled.data))
        
        flash('Bot settings updated successfully.', 'success')
        return redirect(url_for('admin.bot_settings'))
    
    # Get the webhook URL for display
    webhook_url = request.host_url.rstrip('/') + url_for('webhook.line_webhook')
    
    return render_template('bot_settings.html', form=form, webhook_url=webhook_url)

# Bot Styles
@admin_bp.route('/bot_styles')
@admin_required
def bot_styles():
    """Bot styles management page"""
    styles = BotStyle.query.all()
    form = BotStyleForm()
    return render_template('bot_styles.html', styles=styles, form=form)

@admin_bp.route('/bot_styles/add', methods=['GET', 'POST'])
@admin_required
def add_bot_style():
    """Add a new bot style"""
    form = BotStyleForm()
    
    # GET request - render the form
    if request.method == 'GET':
        return render_template('add_bot_style.html', form=form)
    
    if form.validate_on_submit():
        # Check if style name already exists
        existing = BotStyle.query.filter_by(name=form.name.data).first()
        if existing:
            flash(f'A style with name "{form.name.data}" already exists.', 'danger')
            return render_template('add_bot_style.html', form=form)
        
        # Create new style
        style = BotStyle(
            name=form.name.data,
            prompt=form.prompt.data,
            description=form.description.data,
            is_default=form.is_default.data
        )
        
        # If this is set as default, update other styles
        if form.is_default.data:
            BotStyle.query.update({'is_default': False})
            ConfigManager.set("ACTIVE_BOT_STYLE", form.name.data)
        
        db.session.add(style)
        db.session.commit()
        
        flash(f'Style "{form.name.data}" added successfully.', 'success')
        return redirect(url_for('admin.bot_styles'))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
        # If validation fails, return to add form with current values
        return render_template('add_bot_style.html', form=form)
    

@admin_bp.route('/bot_styles/edit/<int:style_id>', methods=['GET', 'POST'])
@admin_required
def edit_bot_style(style_id):
    """Edit an existing bot style"""
    style = BotStyle.query.get_or_404(style_id)
    form = BotStyleForm()
    
    # GET request - populate form with style data
    if request.method == 'GET':
        form.name.data = style.name
        form.prompt.data = style.prompt
        form.description.data = style.description
        form.is_default.data = style.is_default
        return render_template('edit_bot_style.html', style=style, form=form)
    
    if form.validate_on_submit():
        # Check if renaming to an existing name
        if form.name.data != style.name:
            existing = BotStyle.query.filter_by(name=form.name.data).first()
            if existing:
                flash(f'A style with name "{form.name.data}" already exists.', 'danger')
                return redirect(url_for('admin.bot_styles'))
        
        # Update style
        style.name = form.name.data
        style.prompt = form.prompt.data
        style.description = form.description.data
        
        # Handle default status
        if form.is_default.data and not style.is_default:
            BotStyle.query.update({'is_default': False})
            style.is_default = True
            ConfigManager.set("ACTIVE_BOT_STYLE", form.name.data)
        elif form.is_default.data:
            style.is_default = True
            ConfigManager.set("ACTIVE_BOT_STYLE", form.name.data)
        
        db.session.commit()
        
        flash(f'Style "{form.name.data}" updated successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
        # If validation fails, return to edit form with current values
        return render_template('edit_bot_style.html', style=style, form=form)
    
    return redirect(url_for('admin.bot_styles'))

@admin_bp.route('/bot_styles/delete/<int:style_id>', methods=['POST'])
@admin_required
def delete_bot_style(style_id):
    """Delete a bot style"""
    style = BotStyle.query.get_or_404(style_id)
    
    # Don't allow deleting the default style
    if style.is_default:
        flash('Cannot delete the default style.', 'danger')
        return redirect(url_for('admin.bot_styles'))
    
    # Check if this is the active style
    if ConfigManager.get("ACTIVE_BOT_STYLE") == style.name:
        # Find a new default style
        default_style = BotStyle.query.filter_by(is_default=True).first()
        if default_style:
            ConfigManager.set("ACTIVE_BOT_STYLE", default_style.name)
        else:
            # If no default, use the first available
            first_style = BotStyle.query.first()
            if first_style:
                ConfigManager.set("ACTIVE_BOT_STYLE", first_style.name)
                first_style.is_default = True
    
    style_name = style.name
    db.session.delete(style)
    db.session.commit()
    
    flash(f'Style "{style_name}" deleted successfully.', 'success')
    return redirect(url_for('admin.bot_styles'))

@admin_bp.route('/bot_styles/get/<int:style_id>')
@admin_required
def get_bot_style(style_id):
    """Get a bot style as JSON for editing"""
    style = BotStyle.query.get_or_404(style_id)
    return jsonify({
        'id': style.id,
        'name': style.name,
        'prompt': style.prompt,
        'description': style.description,
        'is_default': style.is_default
    })

# Message History
@admin_bp.route('/message_history')
@admin_required
def message_history():
    """Message history page"""
    # Get filter parameters
    user_id = request.args.get('user_id')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Build query
    query = ChatMessage.query
    if user_id:
        query = query.filter_by(line_user_id=user_id)
    
    # Get paginated messages
    messages = query.order_by(ChatMessage.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    # Get all LINE users for filter dropdown
    users = LineUser.query.all()
    
    return render_template('message_history.html', messages=messages, users=users, current_user_id=user_id)

# Knowledge Base
@admin_bp.route('/knowledge_base')
@admin_required
def knowledge_base():
    """Knowledge base management page"""
    documents = Document.query.order_by(Document.uploaded_at.desc()).all()
    form = DocumentForm()
    return render_template('knowledge_base.html', documents=documents, form=form)

@admin_bp.route('/knowledge_base/add', methods=['POST'])
@admin_required
def add_document():
    """Add a document to the knowledge base"""
    form = DocumentForm()
    
    if form.validate_on_submit():
        title = form.title.data
        content = form.content.data
        filename = None
        
        # Handle file upload
        if form.file.data:
            # Process file content
            file = form.file.data
            filename = secure_filename(file.filename)
            
            # Read file content
            file_content = file.read().decode('utf-8', errors='replace')
            
            # If no content was provided in the form, use file content
            if not content:
                content = file_content
        
        # Ensure we have content
        if not content:
            flash('Document must have content either from text field or file.', 'danger')
            return redirect(url_for('admin.knowledge_base'))
        
        # Add document
        success, result = RAGService.add_document(title, content, filename)
        
        if success:
            flash(f'Document "{title}" added successfully.', 'success')
        else:
            flash(f'Error adding document: {result}', 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('admin.knowledge_base'))

@admin_bp.route('/knowledge_base/delete/<int:doc_id>', methods=['POST'])
@admin_required
def delete_document(doc_id):
    """Delete a document from the knowledge base"""
    success, message = RAGService.delete_document(doc_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.knowledge_base'))

@admin_bp.route('/knowledge_base/view/<int:doc_id>')
@admin_required
def view_document(doc_id):
    """View a document's content"""
    document = Document.query.get_or_404(doc_id)
    return jsonify({
        'id': document.id,
        'title': document.title,
        'content': document.content
    })

@admin_bp.route('/knowledge_base/rebuild_index', methods=['POST'])
@admin_required
def rebuild_index():
    """Rebuild the FAISS index"""
    success = RAGService.update_index()
    
    if success:
        flash('Knowledge base index rebuilt successfully.', 'success')
    else:
        flash('Error rebuilding knowledge base index.', 'danger')
    
    return redirect(url_for('admin.knowledge_base'))

# User Management
@admin_bp.route('/user_management')
@admin_required
def user_management():
    """User management page for admin panel users"""
    users = User.query.all()
    form = UserForm()
    return render_template('user_management.html', users=users, form=form)

@admin_bp.route('/user_management/add', methods=['POST'])
@admin_required
def add_user():
    """Add a new admin panel user"""
    form = UserForm()
    
    if form.validate_on_submit():
        # Check if username or email already exists
        if User.query.filter_by(username=form.username.data).first():
            flash(f'Username "{form.username.data}" is already taken.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        if User.query.filter_by(email=form.email.data).first():
            flash(f'Email "{form.email.data}" is already registered.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        # Check for password
        if not form.password.data:
            flash('Password is required for new users.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        # Create new user
        from werkzeug.security import generate_password_hash
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            is_admin=form.is_admin.data
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'User "{form.username.data}" added successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('admin.user_management'))

@admin_bp.route('/user_management/edit/<int:user_id>', methods=['POST'])
@admin_required
def edit_user(user_id):
    """Edit an existing admin panel user"""
    user = User.query.get_or_404(user_id)
    form = UserForm()
    
    # Don't allow non-admin to edit the last admin
    if user.is_admin and not form.is_admin.data:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash('Cannot remove admin status from the last admin user.', 'danger')
            return redirect(url_for('admin.user_management'))
    
    if form.validate_on_submit():
        # Check username and email uniqueness if changed
        if form.username.data != user.username and User.query.filter_by(username=form.username.data).first():
            flash(f'Username "{form.username.data}" is already taken.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        if form.email.data != user.email and User.query.filter_by(email=form.email.data).first():
            flash(f'Email "{form.email.data}" is already registered.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        # Update user
        user.username = form.username.data
        user.email = form.email.data
        user.is_admin = form.is_admin.data
        
        # Update password if provided
        if form.password.data:
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(form.password.data)
        
        db.session.commit()
        
        flash(f'User "{form.username.data}" updated successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('admin.user_management'))

@admin_bp.route('/user_management/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete an admin panel user"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting the last admin
    if user.is_admin:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash('Cannot delete the last admin user.', 'danger')
            return redirect(url_for('admin.user_management'))
    
    # Don't allow deleting self
    if user.id == current_user.id:
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('admin.user_management'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User "{username}" deleted successfully.', 'success')
    return redirect(url_for('admin.user_management'))

@admin_bp.route('/user_management/get/<int:user_id>')
@admin_required
def get_user(user_id):
    """Get a user as JSON for editing"""
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_admin': user.is_admin
    })

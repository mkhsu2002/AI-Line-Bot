from flask import Blueprint, request, jsonify, current_app
from services.llm_service import LLMService
from routes.utils.config_service import is_rag_enabled
from rag_service import RAGService
import logging

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/chat', methods=['POST'])
def chat():
    """API endpoint for testing chat functionality"""
    try:
        data = request.json
        message = data.get('message', '')
        
        if not message:
            return jsonify({'error': '訊息內容不能為空'}), 400
        
        # Get context from knowledge base if RAG is enabled
        rag_context = None
        if is_rag_enabled():
            logger.debug("RAG enabled, retrieving context")
            rag_context = RAGService.get_context_for_query(message)
        
        # Generate response using the LLM service
        response = LLMService.generate_response(message, rag_context=rag_context)
        
        return jsonify({'response': response})
    
    except Exception as e:
        logger.error(f"Error in chat API: {str(e)}", exc_info=True)
        return jsonify({'error': f'處理請求時發生錯誤: {str(e)}'}), 500
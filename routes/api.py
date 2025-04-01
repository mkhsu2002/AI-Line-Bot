from flask import Blueprint, request, jsonify, current_app
from services.llm_service import LLMService
from routes.utils.config_service import is_rag_enabled
from rag_service import RAGService
import logging
import datetime

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/date', methods=['GET'])
def get_date():
    """API endpoint to get the current date and time"""
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
        "full_datetime": current_date.strftime("%Y年%m月%d日 %H:%M:%S"),
        "weekday_chinese": ['一', '二', '三', '四', '五', '六', '日'][current_date.weekday()]
    }
    return jsonify(date_info)

@api_bp.route('/date-test', methods=['GET'])
def test_date_response():
    """API endpoint to test if LLM responds correctly with date information"""
    try:
        # Test with a message asking about the date
        message = "今天是幾號？"
        response = LLMService.generate_response(message)
        
        return jsonify({
            'query': message,
            'response': response,
            'current_date': datetime.datetime.now().strftime("%Y年%m月%d日")
        })
    
    except Exception as e:
        logger.error(f"Error in date test API: {str(e)}", exc_info=True)
        return jsonify({'error': f'處理請求時發生錯誤: {str(e)}'}), 500

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
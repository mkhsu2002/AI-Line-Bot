import os
import logging
import numpy as np
import faiss
import pickle
from models import Document
from app import db
from config import is_rag_enabled
from services.llm_service import LLMService

logger = logging.getLogger(__name__)

class RAGService:
    """Service for Retrieval Augmented Generation (RAG)"""
    
    # Path for storing the FAISS index
    INDEX_PATH = "knowledge_base/faiss_index.idx"
    EMBEDDINGS_PATH = "knowledge_base/embeddings.pkl"
    
    @staticmethod
    def get_embedding(text, client=None):
        """Get embedding for a text using OpenAI API"""
        if client is None:
            client = LLMService.get_client()
            if not client:
                logger.error("Failed to initialize OpenAI client for embeddings")
                return None
        
        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None
    
    @staticmethod
    def initialize_index():
        """Initialize or load the FAISS index"""
        # Create knowledge_base directory if it doesn't exist
        os.makedirs("knowledge_base", exist_ok=True)
        
        # Check if index already exists
        if os.path.exists(RAGService.INDEX_PATH) and os.path.exists(RAGService.EMBEDDINGS_PATH):
            try:
                # Load existing index
                index = faiss.read_index(RAGService.INDEX_PATH)
                with open(RAGService.EMBEDDINGS_PATH, 'rb') as f:
                    doc_embeddings = pickle.load(f)
                logger.info("Loaded existing FAISS index")
                return index, doc_embeddings
            except Exception as e:
                logger.error(f"Error loading FAISS index: {e}")
        
        # Create new index
        logger.info("Creating new FAISS index")
        embedding_dim = 1536  # OpenAI's text-embedding-3-small dimension
        index = faiss.IndexFlatL2(embedding_dim)
        doc_embeddings = {}
        
        return index, doc_embeddings
    
    @staticmethod
    def update_index():
        """Update the FAISS index with all documents in the database"""
        client = LLMService.get_client()
        if not client:
            logger.error("Cannot update index: OpenAI client initialization failed")
            return False
            
        try:
            # Initialize index
            index, doc_embeddings = RAGService.initialize_index()
            
            # Get all active documents
            documents = Document.query.filter_by(is_active=True).all()
            
            # Reset index
            if index.ntotal > 0:
                index.reset()
                doc_embeddings = {}
            
            # Generate embeddings for all documents
            for doc in documents:
                embedding = RAGService.get_embedding(doc.content, client)
                if embedding:
                    # Convert to numpy array and reshape
                    embedding_np = np.array(embedding).astype('float32').reshape(1, -1)
                    
                    # Add to index
                    index.add(embedding_np)
                    doc_embeddings[index.ntotal - 1] = {
                        "id": doc.id,
                        "title": doc.title,
                        "content": doc.content[:1000]  # Store a preview of the content
                    }
            
            # Save index to file
            faiss.write_index(index, RAGService.INDEX_PATH)
            with open(RAGService.EMBEDDINGS_PATH, 'wb') as f:
                pickle.dump(doc_embeddings, f)
                
            logger.info(f"Updated FAISS index with {len(documents)} documents")
            return True
        except Exception as e:
            logger.error(f"Error updating FAISS index: {e}")
            return False
    
    @staticmethod
    def search(query, top_k=3):
        """Search the FAISS index for relevant documents"""
        if not is_rag_enabled():
            logger.info("RAG is disabled, skipping search")
            return None
            
        client = LLMService.get_client()
        if not client:
            logger.error("Cannot search: OpenAI client initialization failed")
            return None
            
        try:
            # Get embedding for query
            query_embedding = RAGService.get_embedding(query, client)
            if not query_embedding:
                return None
                
            query_np = np.array(query_embedding).astype('float32').reshape(1, -1)
            
            # Load index
            index, doc_embeddings = RAGService.initialize_index()
            
            # If index is empty, no results
            if index.ntotal == 0:
                return None
                
            # Search index
            distances, indices = index.search(query_np, min(top_k, index.ntotal))
            
            # Get results
            results = []
            for idx in indices[0]:
                if idx in doc_embeddings:
                    results.append(doc_embeddings[idx])
            
            return results
        except Exception as e:
            logger.error(f"Error searching FAISS index: {e}")
            return None
    
    @staticmethod
    def get_context_for_query(query):
        """Get context from knowledge base for a query"""
        if not is_rag_enabled():
            return None
            
        results = RAGService.search(query)
        if not results:
            return None
            
        # Combine results into a context string
        context = "Knowledge base information:\n\n"
        for i, result in enumerate(results):
            context += f"{i+1}. {result['title']}:\n{result['content']}\n\n"
            
        return context
    
    @staticmethod
    def add_document(title, content, filename=None):
        """Add a document to the database and update the index"""
        try:
            # Add to database
            doc = Document(
                title=title,
                content=content,
                filename=filename,
                is_active=True
            )
            db.session.add(doc)
            db.session.commit()
            
            # Update index
            RAGService.update_index()
            
            return True, doc.id
        except Exception as e:
            logger.error(f"Error adding document: {e}")
            db.session.rollback()
            return False, str(e)
    
    @staticmethod
    def delete_document(doc_id):
        """Delete a document from the database and update the index"""
        try:
            doc = Document.query.get(doc_id)
            if not doc:
                return False, "Document not found"
                
            db.session.delete(doc)
            db.session.commit()
            
            # Update index
            RAGService.update_index()
            
            return True, "Document deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            db.session.rollback()
            return False, str(e)

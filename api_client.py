"""
Genealogy Chatbot API Client Helper
Useful for testing and interacting with the API from Python
"""

import requests
import json
from typing import Dict, List, Optional


class GenealogyAPIClient:
    """Python client for Genealogy Ancestry Chatbot API"""
    
    def __init__(self, base_url: str = "http://localhost:8000/api"):
        self.base_url = base_url
        self.session = requests.Session()
    
    # Document Methods
    def upload_document(
        self, 
        file_path: str, 
        doc_type: str = "journal"
    ) -> Dict:
        """Upload a document"""
        with open(file_path, 'rb') as f:
            files = {'file': f}
            params = {'document_type': doc_type}
            response = self.session.post(
                f"{self.base_url}/documents/upload",
                files=files,
                params=params
            )
        return response.json()
    
    def list_documents(self, doc_type: Optional[str] = None) -> Dict:
        """List all documents"""
        params = {}
        if doc_type:
            params['doc_type'] = doc_type
        response = self.session.get(
            f"{self.base_url}/documents/list",
            params=params
        )
        return response.json()
    
    def get_document(self, document_id: int) -> Dict:
        """Get document details"""
        response = self.session.get(
            f"{self.base_url}/documents/{document_id}"
        )
        return response.json()
    
    def delete_document(self, document_id: int) -> Dict:
        """Delete a document"""
        response = self.session.delete(
            f"{self.base_url}/documents/{document_id}"
        )
        return response.json()
    
    # Query Methods
    def search_ancestry(
        self,
        query: str,
        include_documents: bool = True,
        include_ancestry_data: bool = True
    ) -> Dict:
        """Search genealogical information"""
        data = {
            "query": query,
            "include_documents": include_documents,
            "include_ancestry_data": include_ancestry_data
        }
        response = self.session.post(
            f"{self.base_url}/queries/search",
            json=data
        )
        return response.json()
    
    def ask_chatbot(
        self,
        query: str,
        include_context: bool = True
    ) -> Dict:
        """Ask the genealogy chatbot"""
        data = {
            "query": query,
            "include_context": include_context
        }
        response = self.session.post(
            f"{self.base_url}/queries/ask",
            json=data
        )
        return response.json()
    
    def search_person(self, name: str) -> Dict:
        """Search for a specific person"""
        response = self.session.get(
            f"{self.base_url}/queries/person/{name}"
        )
        return response.json()
    
    def search_family_tree(self, person_name: str) -> Dict:
        """Search family connections"""
        response = self.session.get(
            f"{self.base_url}/queries/family/{person_name}"
        )
        return response.json()
    
    def get_documents_by_type(self, doc_type: str) -> Dict:
        """Get documents by type"""
        response = self.session.get(
            f"{self.base_url}/queries/documents/{doc_type}"
        )
        return response.json()
    
    def get_query_history(self, skip: int = 0, limit: int = 10) -> Dict:
        """Get query history"""
        params = {'skip': skip, 'limit': limit}
        response = self.session.get(
            f"{self.base_url}/queries/history",
            params=params
        )
        return response.json()
    
    # Health Check
    def health_check(self) -> Dict:
        """Check API health"""
        response = self.session.get(
            f"{self.base_url.replace('/api', '')}/health"
        )
        return response.json()


# Example usage
if __name__ == "__main__":
    client = GenealogyAPIClient()
    
    # Check health
    print("Health:", client.health_check())
    
    # Upload a document
    # print("Upload:", client.upload_document("path/to/document.pdf", "journal"))
    
    # List documents
    # print("Documents:", client.list_documents())
    
    # Search person
    # print("Search Person:", client.search_person("John Smith"))
    
    # Ask chatbot
    # print("Chatbot:", client.ask_chatbot("Tell me about African American soldiers"))
    
    # Search family tree
    # print("Family Tree:", client.search_family_tree("John Smith"))

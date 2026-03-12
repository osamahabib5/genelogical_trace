"""
Document processing utilities for extracting text from various formats
"""

import os
import logging
from typing import List, Dict, Tuple
from pathlib import Path
import json

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Process various document formats and extract text"""
    
    SUPPORTED_FORMATS = {'.pdf', '.docx', '.txt', '.json'}
    CHUNK_SIZE = 500  # Characters per chunk
    OVERLAP = 50  # Character overlap between chunks
    
    @staticmethod
    def process_document(file_path: str) -> Tuple[str, List[str]]:
        """
        Process a document and return its full text and chunks
        
        Args:
            file_path: Path to the document
            
        Returns:
            Tuple of (full_text, chunk_list)
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext not in DocumentProcessor.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        if file_ext == '.pdf':
            text = DocumentProcessor._extract_pdf(file_path)
        elif file_ext == '.docx':
            text = DocumentProcessor._extract_docx(file_path)
        elif file_ext == '.txt':
            text = DocumentProcessor._extract_txt(file_path)
        elif file_ext == '.json':
            text = DocumentProcessor._extract_json(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        chunks = DocumentProcessor._chunk_text(text)
        return text, chunks
    
    @staticmethod
    def _extract_pdf(file_path: str) -> str:
        """Extract text from PDF"""
        if PyPDF2 is None:
            raise ImportError("PyPDF2 is not installed")
        
        text = []
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num, page in enumerate(reader.pages):
                    try:
                        text.append(page.extract_text())
                    except Exception as e:
                        logger.warning(f"Error extracting page {page_num}: {e}")
        except Exception as e:
            logger.error(f"Error reading PDF: {e}")
            raise
        
        return '\n'.join(text)
    
    @staticmethod
    def _extract_docx(file_path: str) -> str:
        """Extract text from DOCX"""
        if DocxDocument is None:
            raise ImportError("python-docx is not installed")
        
        try:
            doc = DocxDocument(file_path)
            text = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text.append(para.text)
            
            # Also extract from tables
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            text.append(cell.text)
            
            return '\n'.join(text)
        except Exception as e:
            logger.error(f"Error reading DOCX: {e}")
            raise
    
    @staticmethod
    def _extract_txt(file_path: str) -> str:
        """Extract text from TXT"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            logger.error(f"Error reading TXT: {e}")
            raise
    
    @staticmethod
    def _extract_json(file_path: str) -> str:
        """Extract text from JSON (structured data)"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                return json.dumps(data, indent=2)
        except Exception as e:
            logger.error(f"Error reading JSON: {e}")
            raise
    
    @staticmethod
    def _chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Full text to chunk
            chunk_size: Size of each chunk in characters
            overlap: Overlap between chunks
            
        Returns:
            List of text chunks
        """
        if chunk_size is None:
            chunk_size = DocumentProcessor.CHUNK_SIZE
        if overlap is None:
            overlap = DocumentProcessor.OVERLAP
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk.strip())
            start = end - overlap
        
        return [chunk for chunk in chunks if chunk]  # Remove empty chunks
    
    @staticmethod
    def extract_genealogical_entities(text: str) -> Dict:
        """
        Extract potential genealogical entities from text
        Uses pattern matching to identify names, dates, locations, etc.
        
        Args:
            text: Text to extract entities from
            
        Returns:
            Dictionary with extracted entities
        """
        import re
        
        entities = {
            'names': [],
            'dates': [],
            'locations': [],
            'occupations': [],
            'relationships': []
        }
        
        # Simple patterns (can be enhanced with NLP)
        # Date patterns
        date_pattern = r'\b(?:(?:19|20)\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\n]*?(?:19|20)?\d{2}\b'
        entities['dates'] = list(set(re.findall(date_pattern, text, re.IGNORECASE)))
        
        # Relationship keywords
        relationships = ['father', 'mother', 'son', 'daughter', 'brother', 'sister', 
                        'husband', 'wife', 'grandfather', 'grandmother', 'aunt', 'uncle',
                        'cousin', 'parent', 'child', 'sibling', 'spouse', 'ancestor']
        for rel in relationships:
            if re.search(rf'\b{rel}\b', text, re.IGNORECASE):
                entities['relationships'].append(rel)
        
        # Occupation keywords
        occupations = ['farmer', 'doctor', 'teacher', 'merchant', 'soldier', 'laborer',
                      'carpenter', 'blacksmith', 'nurse', 'cook', 'servant', 'clergy']
        found_occupations = []
        for occ in occupations:
            if re.search(rf'\b{occ}', text, re.IGNORECASE):
                found_occupations.append(occ)
        entities['occupations'] = found_occupations
        
        return entities
